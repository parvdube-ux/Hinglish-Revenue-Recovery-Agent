import unittest
import time
from database import db, Order, Campaign, MessageLog, AuditLogEntry
import agent
import config

class TestRecoveryAgentRules(unittest.TestCase):
    def setUp(self):
        """Reset the in-memory database before each test."""
        db.clear()
        self.order_id = "ord_test_99"
        self.campaign_id = "camp_ord_test_99"
        
        self.order = Order(
            order_id=self.order_id,
            customer_id="cust_test_99",
            customer_name="Rohan Test",
            customer_phone="+919999911111",
            customer_email="test@example.com",
            amount_in_rupees=1000.0,
            status="failed",
            created_at=time.time(),
            failure_reason="unknown",
            bank_error_message="Declined: Insufficient balance in card account"
        )
        db.add_order(self.order)
        
        self.campaign = Campaign(
            campaign_id=self.campaign_id,
            order_id=self.order_id,
            customer_id="cust_test_99",
            created_at=time.time(),
            last_action_at=time.time(),
            persona="cooperative"
        )
        db.add_campaign(self.campaign)

    def test_stop_on_completed_payment(self):
        """Proves that a campaign halts immediately when order status changes to paid."""
        # First check that step 1 sends a nudge
        msg1 = agent.process_recovery_step(self.campaign_id, time.time())
        self.assertIsNotNone(msg1)
        self.assertEqual(self.campaign.outbound_count, 1)
        self.assertEqual(self.campaign.status, "active")
        
        # Simulate customer payment
        self.order.status = "paid"
        
        # Tick the agent again
        msg2 = agent.process_recovery_step(self.campaign_id, time.time() + 3600)
        
        # Verify no message was sent and status transitions to completed_paid
        self.assertIsNone(msg2)
        self.assertEqual(self.campaign.status, "completed_paid")
        self.assertEqual(self.campaign.outbound_count, 1)  # Stays at 1

    def test_stop_on_max_attempts(self):
        """Proves that no more than config.MAX_OUTBOUND_MESSAGES are ever sent."""
        # Check MAX_OUTBOUND_MESSAGES is 3
        self.assertEqual(config.MAX_OUTBOUND_MESSAGES, 3)
        
        # Run 3 attempts
        msg1 = agent.process_recovery_step(self.campaign_id, time.time())
        msg2 = agent.process_recovery_step(self.campaign_id, time.time() + 14400) # 4 hours later
        msg3 = agent.process_recovery_step(self.campaign_id, time.time() + 28800) # 8 hours later
        
        self.assertIsNotNone(msg1)
        self.assertIsNotNone(msg2)
        self.assertIsNotNone(msg3)
        self.assertEqual(self.campaign.outbound_count, 3)
        self.assertEqual(self.campaign.status, "active")
        
        # 4th run should halt and trigger max attempts stop condition
        msg4 = agent.process_recovery_step(self.campaign_id, time.time() + 43200) # 12 hours later
        self.assertIsNone(msg4)
        self.assertEqual(self.campaign.status, "stopped_max_attempts")
        self.assertEqual(self.campaign.outbound_count, 3)  # Did not increment

    def test_stop_on_explicit_opt_out(self):
        """Proves that the campaign halts immediately if the customer replies with negative intent."""
        # Step 1 sent
        msg1 = agent.process_recovery_step(self.campaign_id, time.time())
        self.assertIsNotNone(msg1)
        
        # Simulate customer opt-out reply
        db.log_message(MessageLog(
            campaign_id=self.campaign_id,
            sender="customer",
            text="unsubscribed, nahi chahiye please band karo",
            timestamp=time.time() + 1000
        ))
        
        # Tick the agent
        msg2 = agent.process_recovery_step(self.campaign_id, time.time() + 3600)
        
        # Verify it stops
        self.assertIsNone(msg2)
        self.assertEqual(self.campaign.status, "stopped_opt_out")
        
        # Check that audit log recorded the exact reason
        audit_trail = db.get_audit_trail(self.campaign_id)
        last_audit = audit_trail[-1]
        self.assertIn("stopped_opt_out", last_audit.outcome)
        self.assertIn("anti-spam", last_audit.reasoning)

    def test_stop_on_expiry(self):
        """Proves that the campaign halts when the simulated time exceeds the recovery window."""
        # Tick at t = 0 (Success)
        msg1 = agent.process_recovery_step(self.campaign_id, time.time())
        self.assertIsNotNone(msg1)
        
        # Expiry window is RECOVERY_TIMEOUT_HOURS (default: 24h)
        past_expiry_time = time.time() + (config.RECOVERY_TIMEOUT_HOURS + 1) * 3600
        
        # Tick the agent
        msg2 = agent.process_recovery_step(self.campaign_id, past_expiry_time)
        self.assertIsNone(msg2)
        self.assertEqual(self.campaign.status, "stopped_expired")

    def test_graceful_agent_failure_fallback(self):
        """Proves that a Razorpay API error/timeout is caught and falls back to a merchant URL."""
        # Run step 1 but trigger api timeout
        msg1 = agent.process_recovery_step(self.campaign_id, time.time(), simulate_api_timeout=True)
        
        # Verification:
        # 1. Message should still be successfully generated
        self.assertIsNotNone(msg1)
        # 2. Link in campaign should be fallback URL
        self.assertEqual(self.campaign.payment_link_id, "plink_fallback_err")
        self.assertIn("fallback", self.campaign.payment_link_url)
        # 3. Message should contain the fallback URL
        self.assertIn("fallback", msg1)
        # 4. Outbound count should still increment
        self.assertEqual(self.campaign.outbound_count, 1)
        
        # 5. Check audit trail details for fallback reasoning (Hard Requirement 4)
        audit_trail = db.get_audit_trail(self.campaign_id)
        api_fail_audit = audit_trail[0]
        self.assertIn("failed", api_fail_audit.reasoning)
        self.assertIn("fallback", api_fail_audit.decision)

    def test_external_paid_exclusion_from_agent_recovery(self):
        """Proves that a payment with outbound_count == 0 is excluded from agent-attributed recovery."""
        import simulator
        metrics = simulator.run_simulation()
        
        # Assertions on simulator batch run to prove correct attribution:
        # Organic payments (like external_paid) should be count under completed_paid_organic
        # and rupees_paid_organically, and NOT under rupees_recovered_by_agent
        self.assertEqual(metrics["status_distribution"]["completed_paid_organic"], 4) # 4 external_paid personas
        self.assertEqual(metrics["status_distribution"]["completed_paid_agent_attributed"], 29) # 15 coop + 12 delayed + 2 system_failure = 29
        self.assertGreater(metrics["rupees_recovered_by_agent"], 0.0)
        self.assertGreater(metrics["rupees_paid_organically"], 0.0)
        
        # The recovery rate should be based ONLY on agent recovery (excluding organic payments)
        expected_rate = round((metrics["rupees_recovered_by_agent"] / metrics["rupees_at_risk"]) * 100, 2)
        self.assertEqual(metrics["recovery_rate_pct"], expected_rate)

if __name__ == "__main__":
    unittest.main()
