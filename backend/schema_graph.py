"""
backend/schema_graph.py

FK relationship graph auto-generated from your actual 234-table intern_db schema.
Uses NetworkX BFS to find shortest JOIN path between any two tables.
"""

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

# ── FK graph built directly from your DB's constraint data ───────────────────
# Format: child_table -> { parent_table: "ON child.col = parent.col" }
SCHEMA_GRAPH: dict[str, dict[str, str]] = {
    "ad_and_workgroup": {
        "managed_identity_provider": "ad_and_workgroup.managed_identity_provider_id = managed_identity_provider.id",
    },
    "ad_and_workgroup_connector_agents": {
        "ad_and_workgroup": "ad_and_workgroup_connector_agents.ad_and_workgroup_id = ad_and_workgroup.id",
        "managed_device":   "ad_and_workgroup_connector_agents.connector_agents_id = managed_device.id",
    },
    "agent_command_audit": {
        "managed_device": "agent_command_audit.managed_device_id = managed_device.id",
    },
    "agent_command_queue": {
        "managed_device": "agent_command_queue.managed_device_id = managed_device.id",
    },
    "agent_info": {
        "managed_device": "agent_info.managed_device_id = managed_device.id",
    },
    "alert_criteria": {
        "alert_policies": "alert_criteria.alert_policies_id = alert_policies.id",
    },
    "alert_notification": {
        "alert_policies": "alert_notification.alert_policy_id = alert_policies.id",
    },
    "alert_policies": {
        "policy": "alert_policies.policy_id = policy.id",
    },
    "alerts": {
        "managed_device": "alerts.managed_device_id = managed_device.id",
    },
    "android_device": {
        "managed_device": "android_device.managed_device_id = managed_device.id",
    },
    "android_device_previous_device_names": {
        "android_device": "android_device_previous_device_names.android_device_id = android_device.id",
    },
    "android_enrollment": {
        "enrollment": "android_enrollment.enrollment_id = enrollment.id",
    },
    "application_control_policy": {
        "policy": "application_control_policy.policy_id = policy.id",
    },
    "application_control_policy_target_mapping": {
        "application_control_policy": "application_control_policy_target_mapping.application_control_policy_id = application_control_policy.id",
        "target": "application_control_policy_target_mapping.target_id = target.id",
    },
    "application_control_violations": {
        "managed_device": "application_control_violations.device_id = managed_device.id",
    },
    "application_groups_application_control_policies": {
        "application_control_policy": "application_groups_application_control_policies.application_control_policies_id = application_control_policy.id",
        "application_groups": "application_groups_application_control_policies.application_groups_id = application_groups.id",
    },
    "asset_resource": {
        "managed_device": "asset_resource.resource_id = managed_device.id",
    },
    "battery_details": {
        "asset_resource": "battery_details.asset_id = asset_resource.asset_id",
    },
    "bitlocker_policy_settings": {
        "policy": "bitlocker_policy_settings.policy_id = policy.id",
    },
    "cdrom_drive_details": {
        "asset_resource": "cdrom_drive_details.asset_id = asset_resource.asset_id",
    },
    "certificate_policy": {
        "policy": "certificate_policy.policy_id = policy.id",
    },
    "client": {
        "session": "client.session_id = session.id",
    },
    "command_queue": {
        "managed_device": "command_queue.managed_device_id = managed_device.id",
    },
    "custom_reports": {
        "report": "custom_reports.report_id = report.id",
    },
    "deployment_managed_device": {
        "deployment":     "deployment_managed_device.deployment_id = deployment.id",
        "managed_device": "deployment_managed_device.managed_device_id = managed_device.id",
    },
    "desktop_monitor_details": {
        "asset_resource": "desktop_monitor_details.asset_id = asset_resource.asset_id",
    },
    "device_access_control_policy": {
        "policy": "device_access_control_policy.policy_id = policy.id",
    },
    "device_antivirus": {
        "managed_device": "device_antivirus.managed_device_id = managed_device.id",
    },
    "device_bitlocker": {
        "managed_device": "device_bitlocker.managed_device_id = managed_device.id",
    },
    "device_certificate": {
        "managed_device": "device_certificate.managed_device_id = managed_device.id",
    },
    "device_driver": {
        "driver": "device_driver.driverdd_id = driver.id",
    },
    "device_file_vault_mac": {
        "managed_device": "device_file_vault_mac.managed_device_id = managed_device.id",
    },
    "device_firewall": {
        "managed_device": "device_firewall.managed_device_id = managed_device.id",
    },
    "device_firewall_mac": {
        "managed_device": "device_firewall_mac.managed_device_id = managed_device.id",
    },
    "device_group_members": {
        "managed_device": "device_group_members.managed_device_id = managed_device.id",
    },
    "device_groups": {
        "managed_device": "device_groups.managed_device_id = managed_device.id",
    },
    "device_info": {
        "managed_device":    "device_info.managed_device_id = managed_device.id",
        "asset_manufacturer":"device_info.manufacturer_id = asset_manufacturer.id",
    },
    "device_installed_patch": {
        "managed_device": "device_installed_patch.managed_device_id = managed_device.id",
    },
    "device_location": {
        "managed_device": "device_location.managed_device_id = managed_device.id",
    },
    "device_missing_patch": {
        "managed_device": "device_missing_patch.managed_device_id = managed_device.id",
    },
    "device_network_map": {
        "managed_device": "device_network_map.managed_device_id = managed_device.id",
    },
    "device_operating_system_info": {
        "managed_device": "device_operating_system_info.managed_device_id = managed_device.id",
    },
    "device_patch": {
        "managed_device": "device_patch.managed_device_id = managed_device.id",
    },
    "device_patch_summary": {
        "managed_device": "device_patch_summary.managed_device_id = managed_device.id",
    },
    "device_pricing": {
        "editions": "device_pricing.edition_id = editions.edition_id",
    },
    "device_scan_status": {
        "managed_device": "device_scan_status.managed_device_id = managed_device.id",
    },
    "device_service": {
        "managed_device": "device_service.managed_device_id = managed_device.id",
    },
    "device_shares": {
        "managed_device": "device_shares.managed_device_id = managed_device.id",
    },
    "device_system_users": {
        "managed_device": "device_system_users.managed_device_id = managed_device.id",
        "managed_user":   "device_system_users.managed_user_id = managed_user.id",
    },
    "device_uptime": {
        "managed_device": "device_uptime.managed_device_id = managed_device.id",
    },
    "device_uptime_daily_summary": {
        "managed_device": "device_uptime_daily_summary.managed_device_id = managed_device.id",
    },
    "device_warranty": {
        "managed_device":    "device_warranty.managed_device_id = managed_device.id",
        "asset_manufacturer":"device_warranty.manufacturer_id = asset_manufacturer.id",
    },
    "disk_drive_details": {
        "asset_resource": "disk_drive_details.asset_id = asset_resource.asset_id",
    },
    "driver": {
        "managed_device": "driver.managed_device_id = managed_device.id",
    },
    "dynamic_group_criteria": {
        "zecure_group": "dynamic_group_criteria.zecure_group_id = zecure_group.id",
    },
    "em_role_permissions_mapping": {
        "em_roles":           "em_role_permissions_mapping.id = em_roles.id",
        "em_role_permissions":"em_role_permissions_mapping.role_permission_id = em_role_permissions.role_permission_id",
    },
    "em_user_role": {
        "em_roles": "em_user_role.em_role_id = em_roles.id",
    },
    "enrollment_managed_devices": {
        "managed_device": "enrollment_managed_devices.managed_devices_id = managed_device.id",
        "enrollment":     "enrollment_managed_devices.enrollment_id = enrollment.id",
    },
    "excluded_device_mapping": {
        "target": "excluded_device_mapping.target_id = target.id",
    },
    "excluded_group_mapping": {
        "target": "excluded_group_mapping.target_id = target.id",
    },
    "favorites": {
        "org_members": "favorites.user_id = org_members.id",
    },
    "file_vault_policy": {
        "policy": "file_vault_policy.policy_id = policy.id",
    },
    "firewall_policy": {
        "policy": "firewall_policy.policy_id = policy.id",
    },
    "firewall_rule": {
        "firewall_policy": "firewall_rule.firewall_policy_id = firewall_policy.id",
    },
    "hardware": {
        "asset_manufacturer": "hardware.manufacturer_id = asset_manufacturer.id",
    },
    "hardware_bios": {
        "asset_resource": "hardware_bios.asset_id = asset_resource.asset_id",
    },
    "invoices": {
        "subscriptions": "invoices.subscription_id = subscriptions.subscription_id",
    },
    "keyboard_details": {
        "asset_resource": "keyboard_details.asset_id = asset_resource.asset_id",
    },
    "license_details": {
        "license_status":  "license_details.license_status_id = license_status.id",
        "license_edition": "license_details.license_edition_id = license_edition.id",
        "license_validity":"license_details.license_validity_id = license_validity.id",
        "software":        "license_details.software_id = software.id",
    },
    "license_details_managed_device": {
        "managed_device":  "license_details_managed_device.managed_device_id = managed_device.id",
        "license_details": "license_details_managed_device.license_details_id = license_details.id",
    },
    "license_details_managed_users": {
        "license_details": "license_details_managed_users.license_details_id = license_details.id",
        "managed_user":    "license_details_managed_users.managed_users_id = managed_user.id",
    },
    "license_notification": {
        "license_details": "license_notification.license_details_id = license_details.id",
    },
    "live_session": {
        "session":        "live_session.session_id = session.id",
        "managed_device": "live_session.managed_device_id = managed_device.id",
    },
    "logical_disk_details": {
        "asset_resource": "logical_disk_details.asset_id = asset_resource.asset_id",
    },
    "managed_device_compliance_map": {
        "managed_device": "managed_device_compliance_map.managed_device_id = managed_device.id",
    },
    "managed_device_managed_users": {
        "managed_user":   "managed_device_managed_users.managed_users_id = managed_user.id",
        "managed_device": "managed_device_managed_users.managed_device_id = managed_device.id",
    },
    "managed_device_status": {
        "managed_device": "managed_device_status.managed_device_id = managed_device.id",
    },
    "managed_identity_provider_managed_devices": {
        "managed_identity_provider":"managed_identity_provider_managed_devices.managed_identity_provider_id = managed_identity_provider.id",
        "managed_device":           "managed_identity_provider_managed_devices.managed_devices_id = managed_device.id",
    },
    "managed_identity_provider_managed_users": {
        "managed_identity_provider":"managed_identity_provider_managed_users.managed_identity_provider_id = managed_identity_provider.id",
        "managed_user":             "managed_identity_provider_managed_users.managed_users_id = managed_user.id",
    },
    "managed_policy": {
        "deployment": "managed_policy.deployment_id = deployment.id",
    },
    "managed_user_managed_devices": {
        "managed_device": "managed_user_managed_devices.managed_devices_id = managed_device.id",
        "managed_user":   "managed_user_managed_devices.managed_user_id = managed_user.id",
    },
    "mother_board_details": {
        "asset_resource": "mother_board_details.asset_id = asset_resource.asset_id",
    },
    "network_adapter_details": {
        "asset_resource": "network_adapter_details.asset_id = asset_resource.asset_id",
    },
    "org_members": {
        "roles": "org_members.roles_id = roles.id",
    },
    "patch_deployment_policy": {
        "policy": "patch_deployment_policy.policy_id = policy.id",
    },
    "patch_deployment_policy_target_mapping": {
        "target":                   "patch_deployment_policy_target_mapping.target_id = target.id",
        "patch_deployment_policy":  "patch_deployment_policy_target_mapping.patch_deployment_policy_id = patch_deployment_policy.id",
    },
    "patch_type_mapping": {
        "patch_type": "patch_type_mapping.patch_type_id = patch_type.id",
        "org_patch":  "patch_type_mapping.org_patch_id = org_patch.id",
    },
    "payments": {
        "invoices": "payments.invoice_id = invoices.invoice_id",
    },
    "physical_driver_details": {
        "asset_resource": "physical_driver_details.asset_id = asset_resource.asset_id",
    },
    "physical_memory_details": {
        "asset_resource": "physical_memory_details.asset_id = asset_resource.asset_id",
    },
    "plans": {
        "editions": "plans.edition_id = editions.edition_id",
    },
    "pointing_device": {
        "asset_resource": "pointing_device.asset_id = asset_resource.asset_id",
    },
    "policy": {
        "profiles": "policy.profile_id = profiles.id",
    },
    "policy_patch_mapping": {
        "org_patch":              "policy_patch_mapping.org_patch_id = org_patch.id",
        "patch_deployment_policy":"policy_patch_mapping.policy_id = patch_deployment_policy.id",
    },
    "power_management_policy": {
        "policy": "power_management_policy.policy_id = policy.id",
    },
    "pre_post_check": {
        "pre_post_check_registry":          "pre_post_check.pre_post_check_registry_id = pre_post_check_registry.id",
        "pre_post_check_software_installed":"pre_post_check.pre_post_check_software_installed_id = pre_post_check_software_installed.id",
        "pre_post_check_service_running":   "pre_post_check.pre_post_check_service_running_id = pre_post_check_service_running.id",
        "pre_post_check_disk_space":        "pre_post_check.pre_post_check_disk_space_id = pre_post_check_disk_space.id",
        "pre_post_check_file_folder":       "pre_post_check.pre_post_check_file_folder_id = pre_post_check_file_folder.id",
    },
    "pre_post_custom_script": {
        "pre_post_configuration": "pre_post_custom_script.config_id = pre_post_configuration.id",
    },
    "pre_post_kill_process": {
        "pre_post_configuration": "pre_post_kill_process.config_id = pre_post_configuration.id",
    },
    "pre_post_uninstall_software": {
        "pre_post_configuration": "pre_post_uninstall_software.config_id = pre_post_configuration.id",
    },
    "printer_details": {
        "asset_resource": "printer_details.asset_id = asset_resource.asset_id",
    },
    "processor_details": {
        "asset_resource": "processor_details.asset_id = asset_resource.asset_id",
    },
    "prohibited_software": {
        "software": "prohibited_software.software_id = software.id",
    },
    "registry_entry": {
        "registry_policy": "registry_entry.registry_policy_id = registry_policy.id",
    },
    "registry_policy": {
        "policy": "registry_policy.policy_id = policy.id",
    },
    "report": {
        "reports_type": "report.type_id = reports_type.id",
    },
    "reports_type": {
        "reports_category": "reports_type.category_id = reports_category.id",
    },
    "scan_status": {
        "managed_device": "scan_status.device_id = managed_device.id",
    },
    "scheduled_power_option_policies": {
        "policy": "scheduled_power_option_policies.policy_id = policy.id",
    },
    "scheduled_wake_on_lan_policies": {
        "policy": "scheduled_wake_on_lan_policies.policy_id = policy.id",
    },
    "script_deployment_policy": {
        "policy": "script_deployment_policy.policy_id = policy.id",
    },
    "script_policy_tags_map": {
        "script_tags":   "script_policy_tags_map.tag_id = script_tags.id",
        "script_policy": "script_policy_tags_map.script_policy_id = script_policy.id",
    },
    "script_templates_tags_map": {
        "script_templates": "script_templates_tags_map.script_template_id = script_templates.id",
        "script_tags":      "script_templates_tags_map.tag_id = script_tags.id",
    },
    "serial_port_details": {
        "asset_resource": "serial_port_details.asset_id = asset_resource.asset_id",
    },
    "session": {
        "managed_device": "session.managed_device_id = managed_device.id",
    },
    "smetering_daily_summary": {
        "managed_device": "smetering_daily_summary.managed_device_id = managed_device.id",
    },
    "smetering_device_summary": {
        "managed_device": "smetering_device_summary.managed_device_id = managed_device.id",
    },
    "smetering_usage_raw": {
        "managed_device": "smetering_usage_raw.managed_device_id = managed_device.id",
    },
    "software": {
        "software_category": "software.software_category_id = software_category.id",
        "software_group":    "software.software_group_id = software_group.id",
        "asset_manufacturer":"software.manufacturer_id = asset_manufacturer.id",
    },
    "software_deployment_policy": {
        "policy": "software_deployment_policy.policy_id = policy.id",
    },
    "software_metering_rule": {
        "policy": "software_metering_rule.policy_id = policy.id",
    },
    "software_package": {
        "pre_post_configuration": "software_package.pre_post_install_configuration_id = pre_post_configuration.id",
        "pre_post_check":         "software_package.pre_post_check_id = pre_post_check.id",
        "policy":                 "software_package.policy_id = policy.id",
        "network_share":          "software_package.network_share_id = network_share.id",
        "software_version":       "software_package.software_version_id = software_version.id",
    },
    "software_template": {
        "software_version": "software_template.software_version_id = software_version.id",
    },
    "software_version": {
        "software": "software_version.software_id = software.id",
    },
    "software_version_managed_device": {
        "software_version": "software_version_managed_device.software_version_id = software_version.id",
        "managed_device":   "software_version_managed_device.managed_device_id = managed_device.id",
    },
    "sound_device_details": {
        "asset_resource": "sound_device_details.asset_id = asset_resource.asset_id",
    },
    "subscription_history": {
        "plans":         "subscription_history.old_plan_id = plans.plan_id",
        "subscriptions": "subscription_history.subscription_id = subscriptions.subscription_id",
    },
    "subscriptions": {
        "plans": "subscriptions.plan_id = plans.plan_id",
    },
    "target_device_mapping": {
        "target": "target_device_mapping.target_id = target.id",
    },
    "target_group_mapping": {
        "target": "target_group_mapping.target_id = target.id",
    },
    "tpmdetails": {
        "asset_resource": "tpmdetails.asset_id = asset_resource.asset_id",
    },
    "usb_controller_details": {
        "asset_resource": "usb_controller_details.asset_id = asset_resource.asset_id",
    },
    "usb_hub_details": {
        "asset_resource": "usb_hub_details.asset_id = asset_resource.asset_id",
    },
    "user_confirmation_exclusion": {
        "zecure_group": "user_confirmation_exclusion.zecure_group_id = zecure_group.id",
    },
    "user_logon_history": {
        "managed_user":   "user_logon_history.managed_user_id = managed_user.id",
        "managed_device": "user_logon_history.device_id = managed_device.id",
    },
    "user_management_policy": {
        "policy": "user_management_policy.policy_id = policy.id",
    },
    "video_controller_details": {
        "asset_resource": "video_controller_details.asset_id = asset_resource.asset_id",
    },
    "windows_update_policy": {
        "policy": "windows_update_policy.policy_id = policy.id",
    },
    "zecure_group_dynamic_group_criterias": {
        "zecure_group":          "zecure_group_dynamic_group_criterias.zecure_group_id = zecure_group.id",
        "dynamic_group_criteria":"zecure_group_dynamic_group_criterias.dynamic_group_criterias_id = dynamic_group_criteria.id",
    },
    "zecure_group_managed_devices": {
        "managed_device": "zecure_group_managed_devices.managed_device_id = managed_device.id",
        "zecure_group":   "zecure_group_managed_devices.zecure_group_id = zecure_group.id",
    },
    "zecure_group_members": {
        "org_members":  "zecure_group_members.org_members_id = org_members.id",
        "zecure_group": "zecure_group_members.zecure_group_id = zecure_group.id",
    },
}

# ── Anchor tables ─────────────────────────────────────────────────────────────
ANCHOR_TABLES = {
    "managed_device":    ["device", "machine", "computer", "laptop", "desktop", "endpoint", "workstation", "server"],
    "managed_user":      ["user", "person", "employee", "staff", "who", "username", "logon"],
    "customer":          ["customer", "client", "company", "org", "organisation", "account"],
    "software":          ["software", "app", "application", "program", "tool", "installed"],
    "software_version":  ["version", "release"],
    "agent_info":        ["agent", "heartbeat", "online", "offline", "agent status"],
    "alerts":            ["alert", "alarm", "notification"],
    "policy":            ["policy", "configuration", "setting"],
    "org_patch":         ["patch", "update", "hotfix", "missing patch", "installed patch"],
    "license_details":   ["license", "licence", "seat", "cost", "compliance"],
    "device_antivirus":  ["antivirus", "av", "protection", "virus"],
    "device_bitlocker":  ["bitlocker", "encryption", "encrypted", "drive"],
    "zecure_group":      ["group", "device group", "target group"],
    "profiles":          ["profile", "configuration profile"],
    "deployment":        ["deployment", "deploy", "package"],
    "session":           ["session", "remote session", "live session"],
    "user_logon_history":["login", "logon", "logoff", "sign in"],
}


def _build_graph():
    if not HAS_NX:
        return None
    G = nx.DiGraph()
    for child, parents in SCHEMA_GRAPH.items():
        for parent, on_clause in parents.items():
            G.add_edge(child, parent, join=on_clause)
            G.add_edge(parent, child, join=on_clause)
    return G


_G = _build_graph()


def find_join_path(from_table: str, to_table: str) -> list[str]:
    if not HAS_NX or _G is None:
        return []
    try:
        path = nx.shortest_path(_G, from_table, to_table)
        joins = []
        for i in range(len(path) - 1):
            edge = _G.get_edge_data(path[i], path[i + 1])
            if edge:
                joins.append(f"JOIN {path[i+1]} ON {edge['join']}")
        return joins
    except Exception:
        return []


def get_join_hints(tables: list[str]) -> str:
    if len(tables) <= 1:
        return ""
    root = max(tables, key=lambda t: len(SCHEMA_GRAPH.get(t, {})), default=tables[0])
    seen, result = set(), []
    for table in tables:
        if table == root:
            continue
        for j in find_join_path(root, table):
            if j not in seen:
                seen.add(j)
                result.append(j)
    if not result:
        return ""
    return f"Suggested JOIN path starting from '{root}':\n" + "\n".join(result)


def force_anchor_tables(question: str, retrieved: list[str]) -> list[str]:
    q = question.lower()
    result = list(retrieved)
    for table, keywords in ANCHOR_TABLES.items():
        if any(kw in q for kw in keywords) and table not in result:
            result.insert(0, table)
    return result
