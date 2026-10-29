content = open("frontend/src/layouts/DashboardLayout.tsx").read()
if "/data-quality" not in content:
    if "FactCheck" not in content:
        content = content.replace("  Notifications as NotificationsIcon,\n} from '@mui/icons-material';",
            "  Notifications as NotificationsIcon,\n  FactCheck as FactCheckIcon,\n} from '@mui/icons-material';")
    content = content.replace("  { to: '/audit-logs', label: 'Audit Logs', Icon: AuditIcon, adminOnly: true, strictAdmin: true },\n];",
        "  { to: '/audit-logs', label: 'Audit Logs', Icon: AuditIcon, adminOnly: true, strictAdmin: true },\n  { to: '/data-quality', label: 'Data Quality', Icon: FactCheckIcon, adminOnly: true },\n];")
    open("frontend/src/layouts/DashboardLayout.tsx", "w").write(content)
    print("ok")
else:
    print("exists")
