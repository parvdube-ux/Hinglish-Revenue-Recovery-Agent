import os
import sys
import time
import logging
from database import db, Order, Campaign, MessageLog, AuditLogEntry
import simulator
import agent

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
# Reduce noise from third-party logs
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

def print_banner(title: str):
    print("=" * 65)
    print(f" {title.center(63)}")
    print("=" * 65)

def run_batch_simulation_cli():
    print_banner("RUNNING BATCH RECOVERY SIMULATION (55 CUSTOMER JOURNEYS)")
    print("Running timeline over 24 simulated hours...")
    
    start_time = time.time()
    metrics = simulator.run_simulation()
    duration = time.time() - start_time
    
    print("\nSimulation Completed successfully!")
    print(f"Time Taken: {duration:.2f} seconds")
    print(f"Audit log saved to: {os.path.abspath('recovery_audit_log.csv')}\n")
    
    # Lead with Rupee Amounts (Hard Requirement 2)
    print_banner("REVENUE RECOVERY REPORT CARD")
    print(f"  Total Revenue At Risk:       ₹{metrics['rupees_at_risk']:,.2f}")
    print(f"  Recovered by Agent:          ₹{metrics['rupees_recovered_by_agent']:,.2f}")
    print(f"  Organic/External Payments:   ₹{metrics['rupees_paid_organically']:,.2f}")
    print(f"    (not agent-attributed, shown for completeness — proves double-recovery prevention worked.)")
    print(f"  Total Revenue Lost:          ₹{metrics['rupees_unrecovered']:,.2f}")
    print("-" * 65)
    print(f"  OVERALL RECOVERY RATE:       {metrics['recovery_rate_pct']}%")
    print("=" * 65)
    
    print("\nCampaign Status Distribution:")
    dist = metrics["status_distribution"]
    print(f"  - Completed Paid (Agent-Attributed): {dist.get('completed_paid_agent_attributed', 0)}")
    print(f"  - Completed Paid (Organic/External): {dist.get('completed_paid_organic', 0)}")
    print(f"  - Stopped: Opted Out (Unsub):        {dist.get('stopped_opt_out', 0)}")
    print(f"  - Stopped: Max Nudges Sent (3/3):     {dist.get('stopped_max_attempts', 0)}")
    print(f"  - Stopped: Expired (24h Window):     {dist.get('stopped_expired', 0)}")
    print(f"  - Active (Processing):               {dist.get('active', 0)}")
    print("-" * 65)
    print(f"  Total Journeys Evaluated:           {metrics['total_campaigns']}")
    print("=" * 65)

def inspect_campaign_cli():
    print_banner("INSPECT CAMPAIGN AUDIT TRAIL")
    campaign_ids = list(db.campaigns.keys())
    
    if not campaign_ids:
        print("No campaigns found. Please run the batch simulation first (Option 1).")
        return
        
    print(f"Available Campaigns to inspect ({len(campaign_ids)} total):")
    # Show first 15 campaigns with details
    for idx, cid in enumerate(campaign_ids[:15], 1):
        camp = db.get_campaign(cid)
        order = db.get_order(camp.order_id)
        print(f"  [{idx}] {cid} | Customer: {order.customer_name} | Amount: ₹{order.amount_in_rupees} | Persona: {camp.persona} | Status: {camp.status}")
    
    if len(campaign_ids) > 15:
        print("  ...")
        
    choice = input("\nEnter campaign index to inspect (e.g., 1) or campaign ID: ").strip()
    
    campaign_id = ""
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(campaign_ids):
            campaign_id = campaign_ids[idx]
    else:
        if choice in db.campaigns:
            campaign_id = choice
            
    if not campaign_id:
        print("Invalid campaign selection.")
        return
        
    camp = db.get_campaign(campaign_id)
    order = db.get_order(camp.order_id)
    audit_trail = db.get_audit_trail(campaign_id)
    messages = db.get_messages(campaign_id)
    
    print("\n" + "=" * 65)
    print(f" AUDIT TRAIL FOR CAMPAIGN: {campaign_id} ".center(65, "="))
    print(f"Customer Name:   {order.customer_name} ({camp.persona.upper()} Persona)")
    print(f"Customer Phone:  {order.customer_phone}")
    print(f"Order Amount:    ₹{order.amount_in_rupees:.2f}")
    print(f"Bank Failure:    {order.bank_error_message}")
    print(f"Payment Link:    {camp.payment_link_url or 'None'}")
    print(f"Final Status:    {camp.status.upper()}")
    print("=" * 65)
    
    print("\nMessage Thread Log:")
    if not messages:
        print("  (No messages exchanged)")
    for msg in messages:
        sender_label = "AGENT [SMS/WhatsApp]" if msg.sender == "agent" else "CUSTOMER"
        print(f"  [{sender_label}]: {msg.text}")
        
    print("\nDecision & Reasoning Audits (Hard Requirement 1):")
    for idx, entry in enumerate(audit_trail, 1):
        print(f"\nStep #{idx}:")
        print(f"  [Observation]: {entry.observation}")
        print(f"  [Diagnosis]:   {entry.diagnosis}")
        print(f"  [Decision]:    {entry.decision}")
        print(f"  [Reasoning]:   {entry.reasoning}")
        print(f"  [Action]:      {entry.action_taken}")
        print(f"  [Outcome]:     {entry.outcome}")
        print("-" * 50)

def run_interactive_mode_cli():
    print_banner("INTERACTIVE DEMO MODE")
    print("You will act as the Customer. You can reply in Hinglish, English, or complete the payment.")
    print("The recovery agent will analyze your response and apply stopping/compliance rules.\n")
    
    # Initialize a mock order
    customer_name = input("Enter your name (Default: Rohan Mehra): ").strip() or "Rohan Mehra"
    
    order_id = "ord_interactive"
    campaign_id = "camp_interactive"
    
    # Clean old interactive campaigns if any
    if order_id in db.orders:
        del db.orders[order_id]
    if campaign_id in db.campaigns:
        del db.campaigns[campaign_id]
        
    # Simulate a transaction failure
    print("\nRaw Gateway Error: Declined: Credit limit exceeded")
    
    order = Order(
        order_id=order_id,
        customer_id="cust_interactive",
        customer_name=customer_name,
        customer_phone="+919999988888",
        customer_email="interactive@example.com",
        amount_in_rupees=2499.00,
        status="failed",
        created_at=time.time(),
        failure_reason="unknown",
        bank_error_message="Declined: Credit limit exceeded"
    )
    db.add_order(order)
    
    campaign = Campaign(
        campaign_id=campaign_id,
        order_id=order_id,
        customer_id="cust_interactive",
        created_at=time.time(),
        last_action_at=time.time(),
        persona="interactive"
    )
    db.add_campaign(campaign)

    simulated_now = time.time()
    
    # Process First Outbound Step
    print("\n[System]: Initializing Recovery Agent...")
    time.sleep(1)
    
    # Check if we should simulate API failure
    sim_failure_input = input("Simulate Razorpay API Timeout for graceful failure check? (y/n, Default: n): ").lower().strip()
    simulate_timeout = (sim_failure_input == 'y')
    
    sent_text = agent.process_recovery_step(campaign_id, simulated_now, simulate_api_timeout=simulate_timeout)
    
    if sent_text:
        print(f"\n>>> AGENT SMS: {sent_text}")
    else:
        print(f"\n[System]: No message sent. Campaign is {campaign.status}.")
        return

    # Chat loop (up to 5 steps, though agent halts at 3)
    loop_count = 0
    while campaign.status == "active" and loop_count < 5:
        loop_count += 1
        print("\nYour Options:")
        print("  1. Reply to the agent (e.g. 'nahi chahiye', 'unsubscribed', 'dilao discount', 're-attempting')")
        print("  2. Pay the order (Simulates payment webhook success)")
        print("  3. Exit Chat")
        
        opt = input("Choose option (1-3): ").strip()
        
        if opt == "2":
            # Simulate payment webhook
            order.status = "paid"
            print("\n[Webhook Triggered]: payment.captured status reported to simulator.")
            db.log_message(MessageLog(
                campaign_id=campaign_id,
                sender="customer",
                text="Payment complete.",
                timestamp=time.time()
            ))
            # Tick agent to process payment success
            agent.process_recovery_step(campaign_id, time.time() + (loop_count * 3600))
            print(f"\n[System]: Campaign status updated to: {campaign.status.upper()}")
            break
            
        elif opt == "3":
            break
            
        elif opt == "1":
            user_reply = input("Enter message: ").strip()
            if not user_reply:
                continue
                
            # Log customer reply
            db.log_message(MessageLog(
                campaign_id=campaign_id,
                sender="customer",
                text=user_reply,
                timestamp=time.time()
            ))
            
            print("\n[System]: Processing your response...")
            time.sleep(1)
            
            # Tick agent
            simulated_now += 3600  # Progress time by 1 hour
            sent_text = agent.process_recovery_step(campaign_id, simulated_now)
            
            if sent_text:
                print(f"\n>>> AGENT SMS: {sent_text}")
            else:
                print(f"\n[System]: No message sent. Campaign status is: {campaign.status.upper()}")
                # Print why it stopped
                audit_logs = db.get_audit_trail(campaign_id)
                if audit_logs:
                    print(f"  Halt Reason: {audit_logs[-1].reasoning}")
                break
        else:
            print("Invalid option.")

def main():
    while True:
        print_banner("RAZORPAY BUILDATHON — REVENUE RECOVERY AGENT")
        print("  1. Run Batch Simulation (55 Journeys)")
        print("  2. Inspect Campaign Audit Trail (Hard-Coded Reasoning Logs)")
        print("  3. Run Interactive Demo Mode (CLI Chat)")
        print("  4. Exit")
        print("=" * 65)
        
        choice = input("Enter choice (1-4): ").strip()
        
        if choice == "1":
            run_batch_simulation_cli()
        elif choice == "2":
            inspect_campaign_cli()
        elif choice == "3":
            run_interactive_mode_cli()
        elif choice == "4":
            print("\nExiting. Thank you!")
            sys.exit(0)
        else:
            print("\nInvalid choice. Try again.\n")

if __name__ == "__main__":
    main()
