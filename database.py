import time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

# Schema Models
class Order(BaseModel):
    order_id: str
    customer_id: str
    customer_name: str
    customer_phone: str
    customer_email: str
    amount_in_rupees: float
    status: str  # 'created', 'paid', 'failed', 'refunded', 'disputed'
    created_at: float
    failure_reason: str  # High-level category
    bank_error_message: str  # Raw error text from the bank

class Campaign(BaseModel):
    campaign_id: str
    order_id: str
    customer_id: str
    outbound_count: int = 0
    status: str = "active"  # 'active', 'completed_paid', 'stopped_opt_out', 'stopped_max_attempts', 'stopped_expired', 'suspended_api_failure'
    payment_link_id: Optional[str] = None
    payment_link_url: Optional[str] = None
    created_at: float
    last_action_at: float
    discount_applied_percent: int = 0
    persona: str = "cooperative"  # Used by simulator to guide responses

class AuditLogEntry(BaseModel):
    timestamp: float
    campaign_id: str
    customer_id: str
    observation: str
    diagnosis: str
    decision: str
    reasoning: str
    action_taken: str
    outcome: str

class MessageLog(BaseModel):
    campaign_id: str
    sender: str  # 'agent', 'customer'
    text: str
    timestamp: float

# In-Memory Database
class Database:
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.campaigns: Dict[str, Campaign] = {}
        self.audit_logs: List[AuditLogEntry] = []
        self.message_logs: List[MessageLog] = []

    def clear(self):
        """Clears all records for clean simulation runs."""
        self.orders.clear()
        self.campaigns.clear()
        self.audit_logs.clear()
        self.message_logs.clear()

    # --- Order Operations ---
    def add_order(self, order: Order):
        self.orders[order.order_id] = order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    # --- Campaign Operations ---
    def add_campaign(self, campaign: Campaign):
        self.campaigns[campaign.campaign_id] = campaign

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        return self.campaigns.get(campaign_id)

    def get_campaign_by_order(self, order_id: str) -> Optional[Campaign]:
        for camp in self.campaigns.values():
            if camp.order_id == order_id:
                return camp
        return None

    # --- Audit Logging Operations ---
    def log_audit(self, entry: AuditLogEntry):
        self.audit_logs.append(entry)

    def get_audit_trail(self, campaign_id: str) -> List[AuditLogEntry]:
        return [entry for entry in self.audit_logs if entry.campaign_id == campaign_id]

    # --- Message Logging Operations ---
    def log_message(self, message: MessageLog):
        self.message_logs.append(message)

    def get_messages(self, campaign_id: str) -> List[MessageLog]:
        return [msg for msg in self.message_logs if msg.campaign_id == campaign_id]

# Singleton instance
db = Database()
