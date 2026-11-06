"""Permission catalogue and the 12 default roles from the client deck (slide 10).

Permissions are enforced on the API (see app.core.deps.require). Menus in the
apps are only a convenience built from the same codes.
"""

PERMISSIONS: dict[str, tuple[str, str]] = {
    # code: (module, description)
    "users.view": ("admin", "View users"),
    "users.manage": ("admin", "Create, edit and deactivate users; revoke sessions"),
    "roles.view": ("admin", "View roles and permissions"),
    "roles.manage": ("admin", "Edit roles and their permissions"),
    "settings.manage": ("admin", "Company settings, numbering, integrations"),
    "audit.view": ("governance", "View the audit trail"),
    "branches.view": ("masters", "View branches and warehouses"),
    "branches.manage": ("masters", "Create and edit branches and warehouses"),
    "clients.view": ("masters", "View clients, projects and sites"),
    "clients.manage": ("masters", "Create and edit clients, projects and sites"),
    "items.view": ("masters", "View item master and rate cards"),
    "items.manage": ("masters", "Edit item master and rate cards"),
    "leads.view": ("crm", "View leads and follow-ups"),
    "leads.manage": ("crm", "Create and update leads and follow-ups"),
    "leads.view_all": ("crm", "See every lead in scope, not only own or assigned leads"),
    "clients.credit": ("masters", "Set credit limit, deposit, payment terms and credit status"),
    "stock.view": ("stock", "View stock by warehouse and site"),
    "stock.move": ("stock", "Post stock movements, transfers and status changes"),
    "stock.adjust": ("stock", "Opening stock, stock-check variances and write-offs"),
    "requests.view": ("operations", "View material requests"),
    "requests.create": ("operations", "Raise material requests"),
    "requests.approve": ("operations", "Approve material requests (within value limit)"),
    "dispatch.manage": ("operations", "Pick, verify and dispatch; record returns"),
    "billing.view": ("finance", "View invoices, receipts and dues"),
    "billing.manage": ("finance", "Create invoices, receipts and credit notes"),
    "finance.view": ("finance", "View ledgers and financial reports"),
    "finance.manage": ("finance", "Post journals and close periods"),
    "dashboard.view": ("reports", "View the owner dashboard"),
    "reports.view": ("reports", "View and export reports"),
    "portal.self": ("portal", "Client portal: own requests and statements"),
}

_ALL = set(PERMISSIONS)
_ADMIN = {"users.view", "users.manage", "roles.view", "roles.manage", "settings.manage"}
_MASTERS_VIEW = {"branches.view", "clients.view", "items.view"}

ROLES: dict[str, tuple[str, str, set[str]]] = {
    # code: (name, description, permissions)
    "owner": ("Business Owner", "Full access within policy and value limits", _ALL - {"portal.self"}),
    "general_manager": (
        "General Manager",
        "Runs operations across branches",
        (_ALL - _ADMIN - {"portal.self", "finance.manage"}) | {"users.view", "roles.view"},
    ),
    "branch_manager": (
        "Branch Manager",
        "Runs one or more branches (scoped)",
        _MASTERS_VIEW
        | {"clients.manage", "leads.view", "leads.manage", "leads.view_all", "stock.view", "stock.adjust",
           "requests.view",
           "requests.create", "requests.approve", "billing.view", "reports.view"},
    ),
    "sales": (
        "Sales / CRM Executive",
        "Leads, clients and requests for own accounts",
        _MASTERS_VIEW | {"clients.manage", "leads.view", "leads.manage", "requests.view",
                         "requests.create", "billing.view"},
    ),
    "site_manager": (
        "Site Manager",
        "Requests and receipts for assigned sites",
        {"clients.view", "items.view", "stock.view", "requests.view", "requests.create"},
    ),
    "storekeeper": (
        "Storekeeper",
        "Stock, picking, returns and inspection",
        {"branches.view", "items.view", "stock.view", "stock.move", "requests.view", "dispatch.manage"},
    ),
    "dispatch": (
        "Dispatch & Logistics",
        "Dispatch, challans and transport",
        {"branches.view", "clients.view", "items.view", "stock.view", "stock.move", "requests.view",
         "dispatch.manage"},
    ),
    "accounts_manager": (
        "Accounts Manager",
        "Billing, receivables and the books",
        _MASTERS_VIEW | {"clients.credit", "requests.view", "billing.view", "billing.manage", "finance.view",
                         "finance.manage", "reports.view", "audit.view", "dashboard.view"},
    ),
    "accounts_executive": (
        "Accounts Executive",
        "Invoices and receipts",
        _MASTERS_VIEW | {"billing.view", "billing.manage", "finance.view"},
    ),
    "auditor": (
        "Auditor (read-only)",
        "Reads everything relevant to audit; changes nothing",
        {c for c in _ALL if c.endswith(".view")} - {"users.view"} | {"audit.view", "leads.view_all"},
    ),
    "client_portal": ("Client Portal User", "A client's own requests and statements", {"portal.self"}),
    "sysadmin": ("System Administrator", "Users, roles and settings; no business data", _ADMIN | {"audit.view"}),
}
