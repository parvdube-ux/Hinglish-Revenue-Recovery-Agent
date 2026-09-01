import os
import csv
import time
import random
import logging
from typing import List, Dict, Any
from database import db, Order, Campaign, AuditLogEntry, MessageLog
import agent

logger = logging.getLogger("simulator")

# Preset mock bank error messages for diagnosis
BANK_ERRORS = {
    "insufficient_funds": [
        "Payment failed: Insufficient balance in card account",
        "The customer does not have enough balance to complete this transaction",
        "Declined: Credit limit exceeded",
        "Low balance in bank account linked to UPI"
    ],
    "bank_technical_error": [
        "Gateway Timeout: Bank servers failed to respond",
        "Technical error at issuing bank: Connection timed out",
        "PSP servers are experiencing heavy traffic. Try again later",
        "Bank authentication service unavailable (503 Service Unavailable)"
    ],
    "payment_cancelled": [
        "User closed the payment checkout frame",
        "Payment cancelled by customer during OTP validation",
        "Checkout page abandoned by user",
        "Transaction aborted: back button pressed"
    ],
    "card_declined": [
        "Declined: Incorrect CVV code entered",
        "Payment failed: Invalid card expiration date",
        "Transaction blocked by issuing bank: Card status restricted",
        "Declined: Incorrect UPI PIN entered 3 times"
    ]
}

def generate_synthetic_batch() -> List[Dict[str, Any]]:
    """
    Generates 55 diverse customer profiles with varying personas and error reasons
    to fulfill the 50+ batch simulation requirement (Hard Requirement 6).
    """
    random.seed(42)  # For deterministic simulation runs
    customers = []

    personas = ["cooperative", "delayed", "hostile", "unresponsive", "external_paid", "system_failure"]
    failure_types = list(BANK_ERRORS.keys())

    # Build the distribution (Total: 55 journeys)
    distribution = {
        "cooperative": 15,    # Pays immediately on first reminder nudge
        "delayed": 12,        # Pays on second or third nudge with discount incentive
        "hostile": 10,        # Replies with opt-out keyword after first nudge, triggering hard stop
        "unresponsive": 12,   # Never replies, tests max outbound limit
        "external_paid": 4,   # Pays via alternative channel, tests double-recovery prevention
        "system_failure": 2   # Deliberately fails Razorpay API call, tests graceful fallback path
    }

    cust_id_counter = 1
    order_id_counter = 1001

    for persona, count in distribution.items():
        for _ in range(count):
            # Select random failure type
            fail_type = random.choice(failure_types) if persona != "system_failure" else "bank_technical_error"
            raw_err = random.choice(BANK_ERRORS[fail_type])
            
            # Select random amount (₹250 to ₹10,000)
            amount = round(random.uniform(250.0, 10000.0), 2)
            
            # Simulated names
            names = ["Amit Sharma", "Priya Patel", "Rahul Verma", "Sneha Reddy", "Vikram Singh", 
                     "Ananya Iyer", "Rohan Das", "Kiran Rao", "Meera Nair", "Deepak Gupta"]
            name = random.choice(names) + f" {cust_id_counter}"
            
            customers.append({
                "customer_id": f"cust_{cust_id_counter}",
                "customer_name": name,
                "customer_phone": f"+9198765{cust_id_counter:05d}",
                "customer_email": f"cust_{cust_id_counter}@example.com",
                "order_id": f"ord_{order_id_counter}",
                "amount": amount,
                "persona": persona,
                "raw_error": raw_err
            })
            
            cust_id_counter += 1
            order_id_counter += 1

    return customers

def run_simulation() -> Dict[str, Any]:
    """
    Runs the simulated timeline of 24 hours, driving customer campaigns.
    Returns: Dict containing final rupee-based and campaign-level metrics.
    """
    db.clear()
    customers = generate_synthetic_batch()
    
    # Initialize all orders and campaigns in the database
    sim_time = time.time()
    
    for c in customers:
        order = Order(
            order_id=c["order_id"],
            customer_id=c["customer_id"],
            customer_name=c["customer_name"],
            customer_phone=c["customer_phone"],
            customer_email=c["customer_email"],
            amount_in_rupees=c["amount"],
            status="failed",  # Initially failed order
            created_at=sim_time,
            failure_reason="unknown",  # To be diagnosed by agent
            bank_error_message=c["raw_error"]
        )
        db.add_order(order)
        
        campaign = Campaign(
            campaign_id=f"camp_{c['order_id']}",
            order_id=c["order_id"],
            customer_id=c["customer_id"],
            created_at=sim_time,
            last_action_at=sim_time,
            persona=c["persona"]
        )
        db.add_campaign(campaign)

    # ----------------------------------------------------
    # Drive Timeline (Simulate discrete ticks over 24 hrs)
    # ----------------------------------------------------
    
    # Step 1: Initial Trigger at Hour 0
    for camp_id in db.campaigns.keys():
        camp = db.get_campaign(camp_id)
        if camp.persona == "external_paid":
            # Simulate that the customer paid externally on standard web storefront
            # before the recovery worker cron woke up, so campaign outbound_count stays 0.
            db.get_order(camp.order_id).status = "paid"
            
        # Determine if we force api failure for the system_failure persona
        force_timeout = (camp.persona == "system_failure")
        agent.process_recovery_step(camp_id, sim_time, simulate_api_timeout=force_timeout, is_batch_sim=True)

    # Step 2: Time progresses. Run ticks at Hour 1, Hour 4, Hour 5, Hour 8, Hour 12, Hour 24
    timeline_ticks = [
        {"hours_passed": 1, "desc": "Customer reactions (payment/opt-outs)"},
        {"hours_passed": 4, "desc": "Scheduler: Escalation Nudge 2"},
        {"hours_passed": 5, "desc": "Customer reactions to Nudge 2"},
        {"hours_passed": 8, "desc": "Scheduler: Final Nudge 3"},
        {"hours_passed": 12, "desc": "Scheduler: Hard Limits Check"},
        {"hours_passed": 24, "desc": "Scheduler: Expiry check"}
    ]

    for tick in timeline_ticks:
        tick_time = sim_time + (tick["hours_passed"] * 3600)
        
        # A. Simulate customer actions & external events
        for camp_id, camp in db.campaigns.items():
            order = db.get_order(camp.order_id)
            
            if camp.status != "active":
                continue
            
            # Cooperative Payers: Pay immediately at hour 1
            if camp.persona == "cooperative" and tick["hours_passed"] == 1:
                order.status = "paid"
                # Record payment in checkout history
                db.log_message(MessageLog(
                    campaign_id=camp_id,
                    sender="customer",
                    text="Payment complete. Dynamic link clicked and authorized.",
                    timestamp=tick_time
                ))

            # System Failure (Cooperative) Payers: Pay at hour 1 using the fallback link
            elif camp.persona == "system_failure" and tick["hours_passed"] == 1:
                order.status = "paid"
                db.log_message(MessageLog(
                    campaign_id=camp_id,
                    sender="customer",
                    text="Used fallback link and paid successfully.",
                    timestamp=tick_time
                ))
            
            # Delayed Payers: Pay at hour 5 (after Nudge 2 containing discount) or hour 9 (after Nudge 3)
            elif camp.persona == "delayed":
                if tick["hours_passed"] == 5 and camp.outbound_count == 2:
                    order.status = "paid"
                    db.log_message(MessageLog(
                        campaign_id=camp_id,
                        sender="customer",
                        text="Aapka discount link work kar gaya. Payment is done.",
                        timestamp=tick_time
                    ))
                elif tick["hours_passed"] == 8 and camp.outbound_count == 3:
                    order.status = "paid"
                    db.log_message(MessageLog(
                        campaign_id=camp_id,
                        sender="customer",
                        text="Ok, completed payment now.",
                        timestamp=tick_time
                    ))
            
            # Hostile Opt-outs: Reply "Stop/Nahi chahiye" at hour 1
            elif camp.persona == "hostile" and tick["hours_passed"] == 1:
                db.log_message(MessageLog(
                    campaign_id=camp_id,
                    sender="customer",
                    text="Stop sending me spam messages. Mujhe nahi chahiye.",
                    timestamp=tick_time
                ))
            
            # External Paid: Paid elsewhere at hour 1 (simulates payment status update without using our link)
            elif camp.persona == "external_paid" and tick["hours_passed"] == 1:
                order.status = "paid"
                # No customer message sent (since they checked out on standard web storefront instead)

        # B. Run recovery worker tasks
        for camp_id in db.campaigns.keys():
            # Run the recovery worker agent
            agent.process_recovery_step(camp_id, tick_time, is_batch_sim=True)

    # ----------------------------------------------------
    # Calculate Rupee Metrics (Hard Requirement 2 - Fixed Attribution Bug)
    # ----------------------------------------------------
    total_at_risk = 0.0
    total_recovered_agent = 0.0
    total_paid_organically = 0.0
    total_unrecovered = 0.0
    
    status_counts = {
        "completed_paid_agent_attributed": 0,
        "completed_paid_organic": 0,
        "stopped_opt_out": 0,
        "stopped_max_attempts": 0,
        "stopped_expired": 0,
        "suspended_api_failure": 0,
        "active": 0
    }

    for camp_id, camp in db.campaigns.items():
        order = db.get_order(camp.order_id)
        amount = order.amount_in_rupees
        total_at_risk += amount
        
        # Calculate discount adjustment
        final_amount_paid = amount
        if camp.discount_applied_percent > 0:
            final_amount_paid = amount * (1 - (camp.discount_applied_percent / 100))

        if order.status == "paid":
            if camp.outbound_count > 0:
                total_recovered_agent += final_amount_paid
                status_counts["completed_paid_agent_attributed"] += 1
            else:
                total_paid_organically += final_amount_paid
                status_counts["completed_paid_organic"] += 1
        else:
            total_unrecovered += amount
            status_counts[camp.status] = status_counts.get(camp.status, 0) + 1

    recovery_rate_pct = (total_recovered_agent / total_at_risk * 100) if total_at_risk > 0 else 0.0

    metrics = {
        "rupees_at_risk": round(total_at_risk, 2),
        "rupees_recovered_by_agent": round(total_recovered_agent, 2),
        "rupees_paid_organically": round(total_paid_organically, 2),
        "rupees_unrecovered": round(total_unrecovered, 2),
        "recovery_rate_pct": round(recovery_rate_pct, 2),
        "status_distribution": status_counts,
        "total_campaigns": len(db.campaigns)
    }

    # Write full audit trail to CSV file
    write_audit_log_csv()

    return metrics

def write_audit_log_csv(file_path: str = "recovery_audit_log.csv"):
    """Export the database audit logs to a clean CSV for review."""
    # Write to local project directory
    target_path = os.path.join(os.path.dirname(__file__), file_path)
    
    headers = [
        "Timestamp", "Campaign ID", "Customer ID", 
        "Observation", "Diagnosis & Reasoning", "Decision", 
        "Reasoning Behind Action", "Action Taken", "Outcome"
    ]
    
    try:
        with open(target_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for entry in db.audit_logs:
                writer.writerow([
                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry.timestamp)),
                    entry.campaign_id,
                    entry.customer_id,
                    entry.observation,
                    entry.diagnosis,
                    entry.decision,
                    entry.reasoning,
                    entry.action_taken,
                    entry.outcome
                ])
        logger.info(f"Audit log exported successfully to {target_path}")
    except Exception as e:
        logger.error(f"Failed to export audit logs to CSV: {e}")
