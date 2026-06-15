# NN Fund Management

## Odoo Version
- Odoo 17.0 (Community Edition)

## Installation
1. Clone the repository
2. Copy `.env.example` to `.env` and configure database credentials
3. Run `docker compose up -d`
4. Open `http://localhost:8069`
5. Install the `nn_fund_management` module via Apps menu or:
   ```bash
   docker compose exec odoo odoo -i nn_fund_management --stop-after-init
   ```

## Dependencies
- Docker Engine 20.10+
- Docker Compose v2+
- 2GB RAM minimum (4GB recommended)
- 5GB disk space

## Configuration
1. Edit `.env` to set database credentials
2. For Neon.tech remote PostgreSQL, use the connection details in `.env.example`
3. Configure groups/users via Odoo Settings > Users & Companies > Groups

## Testing
Run the automated test suite:
```bash
docker compose exec odoo odoo -i nn_fund_management --test-enable --stop-after-init -d test_db
```

Or run specific test files:
```bash
docker compose exec odoo odoo -i nn_fund_management --test-enable --test-file=tests/test_fund_balance_logic.py --stop-after-init -d test_db
```

## Assumptions
- Odoo 17.0 Community Edition is sufficient (no Enterprise features required)
- PostgreSQL 15 is used for persistence
- Single-company setup; multi-company record rules are in place but not fully exercised
- Approval workflow defaults to GM then MD unless a `fund.approval.rule` matches
- Bank email parsing (Option C) was skipped; manual incoming fund entry is the primary flow
- OWL Dashboard (Option B) was skipped; kanban/list views provide sufficient visibility

## Known Limitations
- No OWL dashboard component (bonus B skipped - read_group stat cards deferred)
- No bank email parsing prototype (bonus C skipped)
- Configurable approval rules (bonus A) are implemented as a prototype with demo data commented out in `data/fund_approval_rule_demo.xml` - uncomment to enable
- Tests require Docker environment; no standalone pytest runner configured
- Filestore backup strategy not automated (volume snapshots recommended)
- No CI/CD pipeline configured
- Neon.tech integration is untested with this docker-compose setup (intended for production deployment)
