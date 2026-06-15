# NN Fund Management - Technical Assessment

## Odoo Version
- **Odoo 17.0 (Community Edition)**

## Architecture Overview
The module follows a **decoupled, event-driven architecture** centered around a logic-heavy mixin and stored computed fields.
- **FundApprovalMixin:** An abstract model that centralizes the tiered approval logic (GM -> MD). It uses a dynamic rule engine (`fund.approval.rule`) to determine the required steps based on the request amount.
- **Stored Computed Balances:** Instead of manual writes, all financial balances (Allocated, Hold, Spent, Available) are computed dynamically using `@api.depends` in `fund.budget.line`. This ensures data integrity and a clear audit trail.
- **Security & Enforced Controls:** Access is strictly controlled via `ir.model.access.csv` and XML groups. A Python-level constraint prevents "self-approval" of documents unless specifically allowed by a security group.

## Installation & Setup
1. **Dockerized Environment:**
   ```bash
   # Clone the repository
   git clone https://github.com/ashrafalve/nn_fund_management.git
   cd nn_fund_management

   # Start the system
   docker compose up -d
   ```
2. **Initial Configuration:**
   - Log in to Odoo (`http://localhost:8069`) as `admin`.
   - Go to **Settings > Users & Companies > Users**.
   - Open **Administrator** and assign the following groups:
     - **Fund Administrator** (To manage rules)
     - **Self Approval Allowed** (To allow testing the workflow as a single user)

## Testing Instructions (End-to-End)
1. **Incoming Funds:** Create an Incoming Fund for $1,000,000 and click **Confirm**.
2. **Allocation:** Create an Allocation of $200,000 from the account to a **Budget Line**. Approve it (GM then MD).
3. **Requisition:** Create a Requisition for $60,000. 
   - Click **Submit**.
   - Click **GM Approve** (Status changes to `GM Approval`).
   - Click **MD Approve** (Status changes to `Approved`).
4. **Verification:** Go to **Budget Lines**. You will see:
   - **Requisition Hold:** $60,000
   - **Available Balance:** $140,000

## AI Usage Disclosure
- **Tool Used:** Antigravity (AI Coding Assistant).
- **Assistance Provided:** Implementation of the Approval Mixin, generation of boilerplate views, and Docker configuration.
- **Errors Found & Fixed:** 
  - **Security Prefixing:** AI initially generated XML views with unqualified group IDs (e.g., `group_fund_user`). These were manually corrected to `nn_fund_management.group_fund_user` to resolve Odoo 17 `AssertionErrors`.
  - **Self-Approval Bug:** The system correctly identifies the document creator; AI code was enhanced to include a "Self Approval" security group to allow granular control over override permissions.
  - **Sequence Overlap:** Adjusted the sequence numbering for the Requisition states to use `selection_add` patterns to prevent framework warnings.

## Assumptions & Limitations
- **Assumptions:** Single-currency environment (USD used in demo).
- **Limitations:** No bank email parsing (Bonus C) is implemented in this version; all funds are entered manually via the `Incoming Funds` model.

## Required Dependencies
- `base`, `mail`, `project`
