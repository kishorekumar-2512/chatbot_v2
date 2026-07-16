"""
embeddings/build_index.py — 234+ table schema, auto-synced from the live DB.

Run: python -m embeddings.build_index          (incremental — default, fast)
     python -m embeddings.build_index --full    (full rebuild from scratch)

Incremental mode only re-embeds tables whose columns/comments/foreign keys
changed since the last run (by content hash), and drops entries for tables
that no longer exist — safe to run on a schedule (cron) or trigger via
POST /admin/reindex after a cloud deploy, without re-embedding all tables
every time.
"""

import os, sys
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import chromadb

try:
    from embeddings.schema_introspect import introspect_all
except ImportError:
    # Falls back to this when run directly as `python embeddings/build_index.py`
    # rather than `python -m embeddings.build_index` — the project root isn't
    # on sys.path in that invocation style, so add it.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from embeddings.schema_introspect import introspect_all

load_dotenv()
DATABASE_URL    = os.getenv("DATABASE_URL")
CHROMA_DB_PATH  = os.getenv("CHROMA_DB_PATH", "./embeddings/chroma_store")
EMBED_MODEL     = "all-MiniLM-L6-v2"
COLLECTION_NAME = "table_schemas"

RICH_DESCRIPTIONS = {
    "activity_log": (
        "Table 'activity_log' stores audit trail of all user actions and system events. "
        "Contains customer_id, log_module, log_type, user_email, user_name, user_ip, user_agent, remarks. "
        "Use for: activity history, audit log, who did what, user actions, event history, access log."
    ),
    "ad_and_workgroup": (
        "Table 'ad_and_workgroup' stores Active Directory and workgroup configuration for customers. "
        "Contains domain_controller, fqdn, user_name, workgroup_dns_suffix, managed_identity_provider_id, customer_id. "
        "Use for: AD configuration, Active Directory, domain controller, workgroup settings, domain join."
    ),
    "ad_and_workgroup_connector_agents": (
        "Table 'ad_and_workgroup_connector_agents' maps AD/workgroup configs to connector agent devices. "
        "Contains ad_and_workgroup_id, connector_agents_id (managed device). "
        "Use for: AD connector devices, which devices are AD connectors."
    ),
    "affiliate_attribution": (
        "Table 'affiliate_attribution' tracks affiliate marketing attribution for signups. "
        "Contains affiliate_id, affiliate_source, affiliate_meta, product_id, user_id. "
        "Use for: affiliate tracking, marketing source, referral attribution."
    ),
    "agent_command_audit": (
        "Table 'agent_command_audit' stores audit log of commands sent to managed device agents. "
        "Contains command_type, command_status, command_audit_status, command_request, command_sent_times, managed_device_id. "
        "Use for: command history, command audit, what commands were sent to a device, command status."
    ),
    "agent_command_queue": (
        "Table 'agent_command_queue' stores pending commands queued for delivery to managed devices. "
        "Contains command_type, command_status, command_request, managed_device_id, customer_id. "
        "Use for: pending commands, command queue, queued operations for devices."
    ),
    "agent_details_public": (
        "Table 'agent_details_public' stores public agent binary metadata and version details. "
        "Contains agent_type, agent_version, agent_state, agent_purpose, checksum, server_env. "
        "Use for: agent versions available, agent binaries, agent state, agent type."
    ),
    "agent_info": (
        "Table 'agent_info' stores agent installation status on each managed device. "
        "Contains managed_device_id, agent_type, agent_version, agent_status (boolean active/inactive), "
        "upgrade_status, error_code, error_reason, logged_on_users, active_logged_on_users, "
        "last_agent_update_time, agent_upgraded_time, customer_id. "
        "Use for: agent status, active agents, inactive agents, agent version, who is logged on device, "
        "upgrade status, agent errors, devices with inactive agents."
    ),
    "agent_settings": (
        "Table 'agent_settings' stores agent configuration settings per customer. "
        "Contains log_level, log_retention_days, refresh_interval, show_agent_tray, "
        "restrict_uninstall, restrict_binary_termination, user_confirmation, customer_id. "
        "Use for: agent configuration, agent settings, tray visibility, uninstall restriction."
    ),
    "alert_criteria": (
        "Table 'alert_criteria' stores criteria/conditions that trigger alerts in alert policies. "
        "Contains category, sub_category, condition, condition_value, threshold_value, alert_policies_id. "
        "Use for: alert conditions, alert thresholds, what triggers an alert, alert criteria."
    ),
    "alert_notification": (
        "Table 'alert_notification' stores email notification recipients for alert policies. "
        "Contains email, notification_level, alert_policy_id. "
        "Use for: alert recipients, who gets notified, alert email, notification level."
    ),
    "alert_policies": (
        "Table 'alert_policies' defines alert policies with priority and target type. "
        "Contains alert_priority, target_type, policy_id, customer_id. "
        "Use for: alert policy, alert priority, alert configuration."
    ),
    "alerts": (
        "Table 'alerts' stores all alerts raised for managed devices. "
        "Contains managed_device_id, alert_type, severity, status, alert_message, alert_policy_id, customer_id. "
        "Use for: device alerts, active alerts, alert severity, alert status, unresolved alerts, critical alerts."
    ),
    "android_device": (
        "Table 'android_device' stores Android MDM device enrollment details. "
        "Contains managed_device_id, api_level, android_build_number, battery_level, "
        "encryption_status, is_encrypted, management_mode, policy_name, security_patch_level, ownership, customer_id. "
        "Use for: Android devices, MDM Android, battery level, encryption status, Android OS version, "
        "security patch, Android policy."
    ),
    "android_device_previous_device_names": (
        "Table 'android_device_previous_device_names' stores historical device names for Android devices. "
        "Use for: previous device name history, renamed Android devices."
    ),
    "android_enrollment": (
        "Table 'android_enrollment' stores Android MDM enrollment tokens and QR codes. "
        "Contains code, enrollment_url, qr_code, name, customer_id. "
        "Use for: Android enrollment, enrollment token, QR code enrollment."
    ),
    "android_enterprise": (
        "Table 'android_enterprise' stores Android Enterprise (EMM) configuration per customer. "
        "Contains display_name, name, customer_id. "
        "Use for: Android Enterprise, EMM setup, enterprise Android configuration."
    ),
    "application_control_policy": (
        "Table 'application_control_policy' defines policies to allow or block applications. "
        "Contains policy_name, enforcement_action, block_message_title, block_message_reason, policy_id, customer_id. "
        "Use for: application control, app blocking, allowed applications, blocked applications, enforcement policy."
    ),
    "application_control_policy_target_mapping": (
        "Table 'application_control_policy_target_mapping' maps application control policies to targets. "
        "Use for: which devices or groups have application control policies applied."
    ),
    "application_control_violations": (
        "Table 'application_control_violations' records when blocked applications were attempted. "
        "Contains device_name, user_name, application_name, application_group_name, action_taken, policy_name, device_id. "
        "Use for: blocked app attempts, application violations, who tried to run blocked software, policy violations."
    ),
    "application_groups": (
        "Table 'application_groups' defines groups of applications for access control. "
        "Contains application_group_name, access_type, platform, software_count, product_names, vendors, customer_id. "
        "Use for: application groups, app grouping, software groups, allowed/blocked app groups."
    ),
    "application_groups_application_control_policies": (
        "Table 'application_groups_application_control_policies' maps app groups to control policies. "
        "Use for: which policies apply to which application groups."
    ),
    "asset_compliance_summary": (
        "Table 'asset_compliance_summary' stores summary of software compliance counts per entity. "
        "Contains compliance_count, non_compliance_count, license_count, license_expired, "
        "over_license, under_license, in_grace_period_count, summary_entity_id. "
        "Use for: compliance summary, license compliance, over-licensed, under-licensed, compliance counts."
    ),
    "asset_device_summary": (
        "Table 'asset_device_summary' stores device count summary by type (desktop/laptop/server/tablet). "
        "Contains device_count, desktop_count, laptop_count, server_count, tablet_count, others_count. "
        "Use for: device summary, total devices, device types count, how many laptops, servers, desktops."
    ),
    "asset_manufacturer": (
        "Table 'asset_manufacturer' stores hardware manufacturers like Dell, HP, Lenovo. "
        "Contains manufacturer_name, customer_id. "
        "Use for: device manufacturer, hardware brand, manufacturer name, Dell devices, HP devices."
    ),
    "asset_os_summary": (
        "Table 'asset_os_summary' stores OS distribution count (Windows, macOS, Linux, Android, iOS). "
        "Contains windows_os_count, macos_count, linux_os_count, android_os_count, iosos_count. "
        "Use for: OS summary, operating system count, Windows devices, Mac devices, Linux devices."
    ),
    "asset_resource": (
        "Table 'asset_resource' is the bridge table linking hardware assets to managed devices. "
        "Contains asset_id, asset_type, resource_id (managed_device_id), customer_id. "
        "Use for: hardware asset mapping, asset to device link."
    ),
    "asset_total_summary": (
        "Table 'asset_total_summary' stores overall IT asset counts per entity. "
        "Contains total_hardware, total_software, managed_device, total_software_installations, "
        "prohibited_software, in_compliance, over_licensed, under_licensed, devices_with_prohibited_software. "
        "Use for: asset totals, overall summary, prohibited software count, total installations."
    ),
    "battery_details": (
        "Table 'battery_details' stores battery hardware info for laptop batteries. "
        "Contains battery_status, chemical_compound, design_capacity, full_charge_capacity, "
        "estimated_charge_remaining, installed_on, asset_id. "
        "Use for: battery status, battery capacity, battery health, laptop battery details."
    ),
    "bitlocker_policy_settings": (
        "Table 'bitlocker_policy_settings' stores BitLocker drive encryption policy configuration. "
        "Contains drive_encryption_enabled, encryption_method, encrypt_os_drive_only, "
        "enforce_after_days, tpm_auth_type, allow_periodic_rotation, policy_id. "
        "Use for: BitLocker policy, drive encryption settings, TPM authentication, encryption enforcement."
    ),
    "cdrom_drive_details": (
        "Table 'cdrom_drive_details' stores CD/DVD drive hardware details. "
        "Contains description, status, asset_id. "
        "Use for: optical drive, CD drive, DVD drive hardware."
    ),
    "certificate_policy": (
        "Table 'certificate_policy' defines certificate installation/removal policies. "
        "Contains action, certificate_operation, common_name, serial_number, "
        "install_for_all_users_on_device, overwrite_if_certificate_already_exists, policy_id. "
        "Use for: certificate policy, certificate deployment, install certificate, remove certificate."
    ),
    "chargebee_event": (
        "Table 'chargebee_event' stores billing events received from Chargebee payment system. "
        "Contains event_id, event_type. "
        "Use for: billing events, subscription events, payment gateway events."
    ),
    "client": (
        "Table 'client' stores remote support session client connections. "
        "Contains session_id, user_id, role, ip, email, duration, primary_technician, customer_id. "
        "Use for: remote session clients, technician connections, session participants."
    ),
    "command_queue": (
        "Table 'command_queue' stores device commands pending execution. "
        "Contains command, managed_device_id, customer_id. "
        "Use for: queued device commands, pending device actions."
    ),
    "company_details": (
        "Table 'company_details' stores company branding and subdomain configuration. "
        "Contains name, subdomain, company_logo_dfs_id, fav_icon_dfs_id, customer_id. "
        "Use for: company name, subdomain, branding, company logo, white-label settings."
    ),
    "compliance_score_setting": (
        "Table 'compliance_score_setting' stores compliance scoring weights and criteria per platform. "
        "Contains enabled_criteria, percentage, platform, customer_id. "
        "Use for: compliance score configuration, scoring criteria, compliance percentage."
    ),
    "contact": (
        "Table 'contact' stores contact persons for customer accounts. "
        "Contains email, name, customer_id. "
        "Use for: customer contacts, contact email, contact name."
    ),
    "credential_manager": (
        "Table 'credential_manager' stores saved credentials for device access and deployments. "
        "Contains credential_name, credential_type, domain, username, customer_id. "
        "Use for: saved credentials, domain credentials, deployment credentials."
    ),
    "currency_conversion_rates": (
        "Table 'currency_conversion_rates' stores currency exchange rates. "
        "Contains base_currency, target_currency, conversion_rate, is_active. "
        "Use for: currency rates, exchange rate, currency conversion."
    ),
    "custom_reports": (
        "Table 'custom_reports' stores user-created custom report configurations. "
        "Contains report_root, report_columns, filter_criteria, customer_id. "
        "Use for: custom reports, saved reports, report filters."
    ),
    "customer": (
        "Table 'customer' stores all customer accounts managed by the platform. "
        "Contains primary_contact_email, contact_name, country, device_limit, domain_name, "
        "license_model, primary_contact_phone, time_zone, zecure_org_id, alert_at80, alert_at100. "
        "Use for: customer list, customer count, customer email, device limit, customer country, "
        "customer domain, who is the customer, contact details."
    ),
    "customer_members": (
        "Table 'customer_members' maps org members to customers (multi-tenancy). "
        "Contains customer_id, zecure_org_id, org_member_id, zecure_user_id. "
        "Use for: customer members, who has access to a customer, user-to-customer mapping."
    ),
    "deployment": (
        "Table 'deployment' stores software and script deployment tasks. "
        "Contains name, description, deployment_type, deployment_status, creator_zecure_user_id, customer_id. "
        "Use for: deployments, software deployment, deployment status, what is being deployed."
    ),
    "deployment_link": (
        "Table 'deployment_link' stores shareable download links for deployments. "
        "Contains encrypted_url, status, access_count, download_count, expires_at, customer_id. "
        "Use for: deployment links, download links, shared deployment URL."
    ),
    "deployment_managed_device": (
        "Table 'deployment_managed_device' maps deployments to target managed devices. "
        "Contains deployment_id, managed_device_id, status, customer_id. "
        "Use for: deployment targets, which devices have a deployment, deployment status per device."
    ),
    "desktop_monitor_details": (
        "Table 'desktop_monitor_details' stores monitor/display hardware details. "
        "Contains monitor_type, screen_height, screen_width, screen_size, serial_number, status, asset_id. "
        "Use for: monitor details, screen size, display hardware, monitor serial number."
    ),
    "device_access_control_policy": (
        "Table 'device_access_control_policy' defines peripheral device access control (USB, Bluetooth, printers etc). "
        "Contains removable_storage_devices, bluetooth_adapters, cd_rom, printers, keyboards, "
        "wireless_adapters, smart_card_readers, policy_id. "
        "Use for: USB restriction, peripheral control, device access policy, block USB, block Bluetooth."
    ),
    "device_antivirus": (
        "Table 'device_antivirus' stores antivirus product information installed on managed devices. "
        "Contains managed_device_id, antivirus_name, manufacturer, version, protection_status, "
        "licence_status, installation_path, customer_id. "
        "Use for: antivirus status, AV product, protection status, antivirus version, which devices have antivirus."
    ),
    "device_bitlocker": (
        "Table 'device_bitlocker' stores BitLocker drive encryption status per device. "
        "Contains managed_device_id, encryption_status, lock_status, protection_status, "
        "encryption_method, volume_type, logical_drive, recovery_key_status, customer_id. "
        "Use for: BitLocker status, drive encryption, encrypted drives, protection status, recovery key."
    ),
    "device_certificate": (
        "Table 'device_certificate' stores SSL/TLS and security certificates on managed devices. "
        "Contains managed_device_id, friendly_name, issued_by, issued_to, valid_from, valid_to, "
        "status (boolean), is_self_signed_certificate, store_name, key_length, customer_id. "
        "Use for: device certificates, expired certificates, certificate issuer, SSL certificates, certificate status."
    ),
    "device_driver": (
        "Table 'device_driver' stores device driver details installed on managed devices. "
        "Contains driverdd_id, driver_class, driver_version, driver_status, driver_provider, "
        "driver_date, inf_file_name, customer_id. "
        "Use for: device drivers, driver version, driver status, driver class, installed drivers."
    ),
    "device_file_vault_mac": (
        "Table 'device_file_vault_mac' stores macOS FileVault disk encryption status. "
        "Contains managed_device_id, status, encryption_method, file_vault_name, "
        "authenticated_users, customer_id. "
        "Use for: FileVault status, Mac encryption, macOS disk encryption."
    ),
    "device_firewall": (
        "Table 'device_firewall' stores firewall software status on Windows managed devices. "
        "Contains managed_device_id, firewall_name, protection_status, status, "
        "domain_profile_status, public_profile_status, standard_profile_status, customer_id. "
        "Use for: firewall status, Windows firewall, firewall protection, domain/public/private profile."
    ),
    "device_firewall_mac": (
        "Table 'device_firewall_mac' stores macOS firewall status. "
        "Contains managed_device_id, global_state, stealth_enabled, allow_download_signed, status, customer_id. "
        "Use for: Mac firewall, macOS firewall status, stealth mode."
    ),
    "device_group_members": (
        "Table 'device_group_members' stores local user/group membership on managed devices. "
        "Contains managed_device_id, group_sid, device_user_sid, customer_id. "
        "Use for: device local groups, local group membership, SID mapping."
    ),
    "device_groups": (
        "Table 'device_groups' stores local security groups found on managed devices. "
        "Contains managed_device_id, name, sid, domain_name, description, status, customer_id. "
        "Use for: local security groups, device local groups, group SID."
    ),
    "device_info": (
        "Table 'device_info' stores hardware specifications for each managed device. "
        "Contains managed_device_id, processor (CPU: Intel Core i7, AMD Ryzen, Apple M1/M2), "
        "total_ram, used_ram, free_ram, device_model, manufacturer_id, device_type, "
        "hard_disk_free_space, hard_disk_used_space, device_internal_storage, "
        "device_fqdn_name, device_service_tag, dhcp_address, domain_role, customer_id. "
        "Use for: processor type, CPU, Intel, AMD, RAM, free RAM, disk space, device model, "
        "hardware specs, which device has Intel i7, RAM size, total RAM, free disk space."
    ),
    "device_installed_patch": (
        "Table 'device_installed_patch' records patches successfully installed on each device. "
        "Contains managed_device_id, patch_id, master_patch_id, last_deployment_at, customer_id. "
        "Use for: installed patches, patch installation history, which patches are installed."
    ),
    "device_location": (
        "Table 'device_location' stores GPS/network location data for managed devices. "
        "Contains managed_device_id, latitude, longitude, address, geo_source, network_type, customer_id. "
        "Use for: device location, GPS coordinates, device address, where is the device."
    ),
    "device_missing_patch": (
        "Table 'device_missing_patch' records patches that are missing (not installed) on devices. "
        "Contains managed_device_id, patch_id, master_patch_id, customer_id. "
        "Use for: missing patches, unpatched devices, patches not installed, patch compliance."
    ),
    "device_network_map": (
        "Table 'device_network_map' stores network identity information for managed devices. "
        "Contains managed_device_id, ip_address, mac_address, subnetmask, broadcast_address, "
        "domain_name, domain_controller_name, customer_id. "
        "Use for: device IP address, MAC address, subnet, domain controller, network mapping."
    ),
    "device_operating_system_info": (
        "Table 'device_operating_system_info' stores OS details for each managed device. "
        "Contains managed_device_id, os_name, os_version, os_architecture, os_build_number, "
        "os_family, os_language, os_license_status, os_license_type, service_pack, customer_id. "
        "Use for: OS name, OS version, Windows version, macOS version, OS architecture, "
        "OS license status, service pack, OS family."
    ),
    "device_patch": (
        "Table 'device_patch' stores patch deployment status (installed/missing) per device. "
        "Contains managed_device_id, patch_id, install_status, last_deployment_at, customer_id. "
        "Use for: patch status per device, install status, patch deployment result."
    ),
    "device_patch_summary": (
        "Table 'device_patch_summary' stores patch counts summary per device. "
        "Contains managed_device_id, installed_count, missing_count, customer_id. "
        "Use for: patch summary, how many patches installed, how many patches missing per device."
    ),
    "device_pricing": (
        "Table 'device_pricing' stores pricing tiers for device count ranges. "
        "Contains min_devices, max_devices, monthly_price, yearly_price, product_id, edition_id. "
        "Use for: device pricing, pricing tiers, cost per device range."
    ),
    "device_scan_status": (
        "Table 'device_scan_status' stores the current scan status and timing for each device. "
        "Contains managed_device_id, status, last_successful_scan, last_initiated_time, remarks. "
        "Use for: scan status, last scan time, scan success, scan failure, devices not scanned."
    ),
    "device_service": (
        "Table 'device_service' stores Windows services running on managed devices. "
        "Contains managed_device_id, name, display_name, status, start_mode, service_type, "
        "log_on_name, path_name, customer_id. "
        "Use for: Windows services, service status, running services, stopped services, service name."
    ),
    "device_shares": (
        "Table 'device_shares' stores network shares configured on managed devices. "
        "Contains managed_device_id, name, path, type, description, user_limit, customer_id. "
        "Use for: network shares, shared folders, shared paths on devices."
    ),
    "device_system_users": (
        "Table 'device_system_users' stores local user accounts on each managed device. "
        "Contains managed_device_id, managed_user_id, name, full_name, sid, domain, "
        "is_administrator, is_disabled, is_local_account, is_lockout, account_type, customer_id. "
        "Use for: local users, system users, administrator accounts, disabled accounts, "
        "locked accounts, who has admin rights on a device."
    ),
    "device_uptime": (
        "Table 'device_uptime' stores device power events (boot, shutdown, sleep). "
        "Contains managed_device_id, event_type, event_time, event_end_time, "
        "shutdown_reason, battery_level, previous_shutdown_time, interval_seconds, customer_id. "
        "Use for: device uptime, shutdown events, boot time, power events, battery level history."
    ),
    "device_uptime_daily_summary": (
        "Table 'device_uptime_daily_summary' stores daily availability percentages per device. "
        "Contains managed_device_id, availability, total_uptime, total_downtime, power_cycle_count, customer_id. "
        "Use for: device availability, uptime percentage, downtime, power cycles per day."
    ),
    "device_warranty": (
        "Table 'device_warranty' stores warranty information for managed devices. "
        "Contains managed_device_id, manufacturer_id, warranty_status, warranty_type, "
        "warranty_start_date, warranty_end_date, warranty_provider, warranty_duration, customer_id. "
        "Use for: warranty status, warranty expiry, expired warranty, warranty type, warranty provider."
    ),
    "dfs_files": (
        "Table 'dfs_files' stores file storage metadata for uploaded files (logs, reports, packages). "
        "Contains file_name, file_type, file_size, bucket_name, storage_path, download_url, customer_id. "
        "Use for: stored files, file metadata, uploaded files, file type, file size."
    ),
    "disk_drive_details": (
        "Table 'disk_drive_details' stores physical disk drive hardware info. "
        "Contains asset_id, description, total_size, free_space, status. "
        "Use for: disk drive size, free space, disk status, physical disk."
    ),
    "driver": (
        "Table 'driver' stores device drivers installed on managed devices. "
        "Contains managed_device_id, driver_name, driver_type, manufacturer_name, customer_id. "
        "Use for: installed drivers, driver name, driver type, driver manufacturer."
    ),
    "dynamic_group_criteria": (
        "Table 'dynamic_group_criteria' stores filter criteria for dynamic device groups. "
        "Contains zecure_group_id, criteria_field, criteria_operator, criteria_value, "
        "criteria_logical_operator, customer_id. "
        "Use for: dynamic group rules, auto-group criteria, group filter conditions."
    ),
    "editions": (
        "Table 'editions' stores product edition tiers (Standard, Professional, Enterprise). "
        "Contains edition_id, name, description, product_id, rank, status. "
        "Use for: product editions, tier names, edition hierarchy."
    ),
    "em_audit": (
        "Table 'em_audit' stores admin audit log for management console actions. "
        "Contains action, authored_by, ip_address, status, error, user_id, zecure_org_id. "
        "Use for: admin actions audit, management audit, who did what in admin console."
    ),
    "em_org_info": (
        "Table 'em_org_info' stores organization-level agent state and server environment config. "
        "Contains zecure_org_id, agent_state_windows, agent_state_mac, agent_state_linux, server_env. "
        "Use for: org configuration, agent state per OS, server environment."
    ),
    "em_role_permissions": (
        "Table 'em_role_permissions' defines granular permissions per module and sub-module. "
        "Contains module, sub_module, access. "
        "Use for: permissions, module access, role permissions, what actions are allowed."
    ),
    "em_role_permissions_mapping": (
        "Table 'em_role_permissions_mapping' maps role permission sets to roles. "
        "Use for: role to permission mapping."
    ),
    "em_roles": (
        "Table 'em_roles' defines technician/admin roles in the management console. "
        "Contains role_name, role_type, description, editable, zecure_org_id. "
        "Use for: admin roles, technician roles, role names, role types."
    ),
    "em_user_role": (
        "Table 'em_user_role' maps users to their management console roles. "
        "Contains user_id, em_role_id, zecure_org_id. "
        "Use for: user role assignment, which role does a user have, role mapping."
    ),
    "enrollment": (
        "Table 'enrollment' stores device enrollment tokens for onboarding new devices. "
        "Contains enrollment_token, type, expires_in, expires_after_once, customer_id. "
        "Use for: enrollment tokens, device onboarding, enrollment type, token expiry."
    ),
    "enrollment_managed_devices": (
        "Table 'enrollment_managed_devices' links enrolled devices to their enrollment record. "
        "Use for: which devices were enrolled via which token."
    ),
    "excluded_device_mapping": (
        "Table 'excluded_device_mapping' stores devices explicitly excluded from policy targets. "
        "Contains target_id, device_id, group_id, is_associated_from_group, remarks, customer_id. "
        "Use for: excluded devices, devices excluded from policy, exclusion list."
    ),
    "excluded_group_mapping": (
        "Table 'excluded_group_mapping' stores groups excluded from policy targets. "
        "Contains target_id, group_id, remarks, customer_id. "
        "Use for: excluded groups, groups excluded from a policy."
    ),
    "favorites": (
        "Table 'favorites' stores items bookmarked/favorited by users. "
        "Contains user_id, item_id, item_type, customer_id. "
        "Use for: user favorites, bookmarked items, starred items."
    ),
    "file_vault_policy": (
        "Table 'file_vault_policy' stores macOS FileVault encryption policy settings. "
        "Contains drive_encryption_enabled, store_recovery_key, allow_periodic_rotation, "
        "rotation_period_days, policy_id. "
        "Use for: FileVault policy, Mac encryption policy, recovery key policy."
    ),
    "firewall_policy": (
        "Table 'firewall_policy' stores Windows Firewall policy configuration. "
        "Contains domain_inbound, domain_outbound, private_inbound, private_outbound, "
        "public_inbound, public_outbound, policy_id. "
        "Use for: firewall policy, inbound rules, outbound rules, network profile firewall."
    ),
    "firewall_rule": (
        "Table 'firewall_rule' stores individual firewall rules within a firewall policy. "
        "Contains rule_name, action, direction, protocol, local_ports, remote_ports, "
        "program_path, is_domain_enabled, is_private_enabled, is_public_enabled, firewall_policy_id. "
        "Use for: firewall rules, allow/block rules, port rules, protocol rules, rule direction."
    ),
    "geo_location_settings": (
        "Table 'geo_location_settings' stores GPS tracking configuration per customer. "
        "Contains tracking_enabled, history_enabled, tracking_scope, customer_id. "
        "Use for: geo tracking settings, location tracking enabled, tracking scope."
    ),
    "geo_tracking_groups": (
        "Table 'geo_tracking_groups' specifies which groups are tracked for geo location. "
        "Contains geo_location_settings_id, group_id, customer_id. "
        "Use for: tracked groups, location tracking groups."
    ),
    "hardware": (
        "Table 'hardware' stores hardware asset catalogue entries. "
        "Contains hardware_name, hardware_type, status, manufacturer_id, customer_id. "
        "Use for: hardware assets, hardware type, hardware status, manufacturer."
    ),
    "hardware_bios": (
        "Table 'hardware_bios' stores BIOS information for devices. "
        "Contains asset_id, smbiosbiosversion, serial_number, release_date, version, status. "
        "Use for: BIOS version, BIOS release date, BIOS serial number."
    ),
    "hardware_managed_devices": (
        "Table 'hardware_managed_devices' maps hardware assets to managed devices. "
        "Contains hardware_id, managed_devices_id, count, unique_identifier, customer_id. "
        "Use for: hardware to device mapping, which hardware is on which device."
    ),
    "hardware_type": (
        "Table 'hardware_type' is a lookup for hardware type codes and names. "
        "Use for: hardware type name lookup."
    ),
    "ide_controller_details": (
        "Table 'ide_controller_details' stores IDE controller hardware info. "
        "Contains status, customer_id. "
        "Use for: IDE controller status, IDE hardware."
    ),
    "invoices": (
        "Table 'invoices' stores billing invoices for subscriptions. "
        "Contains invoice_number, total_amount, currency, status, issued_date, due_date, "
        "subscription_id, zecure_org_id. "
        "Use for: invoices, billing, invoice amount, payment status, due invoices."
    ),
    "key_value": (
        "Table 'key_value' stores generic configuration key-value pairs per customer. "
        "Use for: configuration values, settings key-value, custom configuration."
    ),
    "keyboard_details": (
        "Table 'keyboard_details' stores keyboard hardware details. "
        "Contains description, number_of_function_keys, status, asset_id. "
        "Use for: keyboard hardware, keyboard type, keyboard status."
    ),
    "license_details": (
        "Table 'license_details' stores software license purchase records. "
        "Contains software_id, license_type, cost, currency_type, license_purchased, "
        "compliant_status, purchase_date, reseller_name, version, vendor_id, "
        "device_license, is_device_compliance, license_status_id, license_validity_id, customer_id. "
        "Use for: licenses, license cost, license compliance, purchased licenses, compliant status, "
        "reseller, license type, how many licenses purchased, license expiry."
    ),
    "license_details_managed_device": (
        "Table 'license_details_managed_device' maps licenses to the devices they are assigned to. "
        "Use for: license per device, which devices have a license, device license assignment."
    ),
    "license_details_managed_users": (
        "Table 'license_details_managed_users' maps licenses to the users they are assigned to. "
        "Use for: license per user, which users have a license, user license assignment."
    ),
    "license_edition": (
        "Table 'license_edition' stores edition information for software licenses. "
        "Contains license_edition, customer_id. "
        "Use for: license edition, software edition in license."
    ),
    "license_notification": (
        "Table 'license_notification' stores license expiry and renewal notification settings. "
        "Contains license_details_id, expiry_interval, reminder_interval, expiry_mail, reminder_mail. "
        "Use for: license expiry notifications, renewal reminders, license alerts."
    ),
    "license_status": (
        "Table 'license_status' stores license status types (active, expired, trial). "
        "Contains license_status, source, usage_environment, comments, customer_id. "
        "Use for: license status, license source, usage environment."
    ),
    "license_validity": (
        "Table 'license_validity' stores license key and validity dates. "
        "Contains activation_date, expiry_date, renewal_date, grace_period, license_key. "
        "Use for: license key, license expiry date, activation date, renewal date, grace period."
    ),
    "live_session": (
        "Table 'live_session' stores active remote support sessions. "
        "Contains managed_device_id, session_id, session_type, customer_id. "
        "Use for: live remote sessions, active sessions, remote support in progress."
    ),
    "logical_disk_details": (
        "Table 'logical_disk_details' stores logical drive/partition details per device. "
        "Contains asset_id, name (drive letter), file_system, total_size, free_space, drive_type, status. "
        "Use for: drive partitions, C drive, D drive, free disk space, file system, drive type."
    ),
    "managed_device": (
        "Table 'managed_device' is the central table for all managed endpoints and computers. "
        "Contains customer_id, device_name, domain_name, device_type, platform (integer: 1=Windows/2=Mac/3=Linux), "
        "status (integer: 1=active/2=inactive), service_tag, deviceuuid, installed_time, zecure_org_id. "
        "Use for: device list, device name, device platform, Windows devices, Mac devices, Linux devices, "
        "device status, active devices, inactive devices, device count, devices per customer."
    ),
    "managed_device_compliance_map": (
        "Table 'managed_device_compliance_map' stores compliance score and status per device. "
        "Contains managed_device_id, compliance_score, compliant_status, percentage, customer_id. "
        "Use for: device compliance score, compliance status, compliance percentage, non-compliant devices."
    ),
    "managed_device_managed_users": (
        "Table 'managed_device_managed_users' maps managed devices to managed users (many-to-many). "
        "Use for: which users are associated with which devices, user-device mapping."
    ),
    "managed_device_status": (
        "Table 'managed_device_status' stores detailed device status and recent action results. "
        "Contains managed_device_id, status, reported_at, completed_at, power_options, customer_id. "
        "Use for: device action status, recent device operations, power state."
    ),
    "managed_identity_provider": (
        "Table 'managed_identity_provider' stores identity provider (AD, Azure AD) sync config. "
        "Contains name, type, sync_status, last_sync_time, sync_failure_reason, customer_id. "
        "Use for: identity provider, AD sync, Azure AD, sync status, last sync time."
    ),
    "managed_identity_provider_managed_devices": (
        "Table 'managed_identity_provider_managed_devices' maps identity providers to managed devices. "
        "Use for: which devices came from which identity provider."
    ),
    "managed_identity_provider_managed_users": (
        "Table 'managed_identity_provider_managed_users' maps identity providers to managed users. "
        "Use for: which users came from which identity provider, AD-synced users."
    ),
    "managed_policy": (
        "Table 'managed_policy' stores Android MDM policy data linked to deployments. "
        "Contains deployment_id, android_policy_data, customer_id. "
        "Use for: Android MDM policy, mobile policy data."
    ),
    "managed_user": (
        "Table 'managed_user' stores all managed user accounts. "
        "Contains customer_id, email, username, domain, sid, objectguid, zecure_org_id. "
        "Use for: users, user list, username, user email, user domain, user count, "
        "which users exist, SID, user account."
    ),
    "managed_user_account_info": (
        "Table 'managed_user_account_info' stores detailed AD account info for managed users. "
        "Contains first_name, last_name, department, job_title, email (user_principle_name), "
        "is_enabled, is_locked_out, is_password_expired, last_log_on_date_time, "
        "last_log_off_date_time, manager, city, country, mobile_phone. "
        "Use for: user department, job title, locked accounts, disabled accounts, "
        "last login time, expired passwords, user full name, manager, city, phone."
    ),
    "managed_user_managed_devices": (
        "Table 'managed_user_managed_devices' maps users to their managed devices. "
        "Use for: user devices, which devices belong to a user, user device mapping."
    ),
    "mother_board_details": (
        "Table 'mother_board_details' stores motherboard hardware details. "
        "Contains model, name, product, serial_number, version, status, asset_id. "
        "Use for: motherboard model, motherboard version, system board details."
    ),
    "network_adapter_details": (
        "Table 'network_adapter_details' stores network interface card (NIC) details. "
        "Contains asset_id, ip_addr, mac_address, dns_host_name, dhcp_server, "
        "is_dhcp_enabled, network_bandwidth, connection_status. "
        "Use for: network adapter, NIC, IP address, MAC address, DHCP, network bandwidth."
    ),
    "network_share": (
        "Table 'network_share' stores network share credentials used in deployments. "
        "Contains network_share_path, username, customer_id. "
        "Use for: network share path, UNC path, share credentials."
    ),
    "offers": (
        "Table 'offers' stores review/referral offers for customers. "
        "Contains customer_id, review_platform, review_link, status, product_id. "
        "Use for: offers, review offers, referral status."
    ),
    "org_data_cleanup_settings": (
        "Table 'org_data_cleanup_settings' stores data retention/cleanup periods per org. "
        "Contains activity_log_retention_period, alert_retention_period, "
        "geo_location_history_retention_period, user_logon_history_retention_period, zecure_org_id. "
        "Use for: data retention policy, cleanup settings, how long data is kept."
    ),
    "org_members": (
        "Table 'org_members' stores technicians and admin users who access the management platform. "
        "Contains email_id, username, roles_id, status, device_access, invited_by, "
        "joined_at, zecure_org_id. "
        "Use for: technicians, admin users, org members, who has platform access, member roles."
    ),
    "org_patch": (
        "Table 'org_patch' stores patches available in the org's patch repository. "
        "Contains patch_id, title, description, severity, categories, patch_family, "
        "kb_number, is_mandatory, approved, reboot_required, master_patch_id, customer_id. "
        "Use for: available patches, patch severity, critical patches, patch title, KB number, "
        "mandatory patches, approved patches, reboot required patches."
    ),
    "org_preference": (
        "Table 'org_preference' stores organization-level preferences. "
        "Contains auto_map_group_device_associations, quick_setup_enabled, zecure_org_id. "
        "Use for: org preferences, auto mapping, quick setup."
    ),
    "patch_deployment_policy": (
        "Table 'patch_deployment_policy' defines how patches are deployed (schedule, retry, notifications). "
        "Contains policy_id, retry_count, retry_interval, retry_on_failure, "
        "notify_on_success, notify_on_failure, notification_emails, schedule_jobs_id. "
        "Use for: patch deployment settings, patch schedule, retry policy, patch notifications."
    ),
    "patch_deployment_policy_target_mapping": (
        "Table 'patch_deployment_policy_target_mapping' maps patch policies to target devices/groups. "
        "Use for: which devices or groups get a patch deployment policy."
    ),
    "patch_type": (
        "Table 'patch_type' is a lookup for patch categories (Security, Critical, Feature). "
        "Contains name, description. "
        "Use for: patch type name, patch category."
    ),
    "patch_type_mapping": (
        "Table 'patch_type_mapping' maps org patches to their patch type categories. "
        "Use for: patch classification, which category a patch belongs to."
    ),
    "payment_methods": (
        "Table 'payment_methods' stores saved payment cards for billing. "
        "Contains card_brand, last4digits, expiry_month, expiry_year, is_default, "
        "payment_gateway, type, zecure_org_id. "
        "Use for: saved cards, payment method, default card, card details."
    ),
    "payments": (
        "Table 'payments' stores payment transaction records. "
        "Contains invoice_id, amount, currency, transaction_status, payment_method, "
        "gateway_payment_id, transaction_date, zecure_org_id. "
        "Use for: payment transactions, payment status, paid invoices, payment amount."
    ),
    "pcmcia_controller_details": (
        "Table 'pcmcia_controller_details' stores PCMCIA card controller hardware info. "
        "Use for: PCMCIA hardware, card reader controllers."
    ),
    "pending_delete": (
        "Table 'pending_delete' tracks entities queued for deletion. "
        "Contains entity_id, entity_type, last_attempted_at, zecure_org_id. "
        "Use for: pending deletions, queued cleanup."
    ),
    "physical_driver_details": (
        "Table 'physical_driver_details' stores physical disk drive hardware details. "
        "Contains model, serial_number, size, media_type, partitions, asset_id. "
        "Use for: physical disk model, disk size, disk serial number, disk media type."
    ),
    "physical_memory_details": (
        "Table 'physical_memory_details' stores RAM slot and memory hardware info. "
        "Contains location, max_supportedram, no_of_slots, asset_id. "
        "Use for: RAM slots, memory location, maximum supported RAM."
    ),
    "plans": (
        "Table 'plans' stores subscription plans with pricing and limits. "
        "Contains name, plan_type, billing_period, currency, max_devices, max_technicians, "
        "free_technicians, duration_days, grace_period_days, plan_features, product_id, edition_id. "
        "Use for: subscription plans, plan pricing, max devices per plan, plan features, plan type."
    ),
    "policy": (
        "Table 'policy' is the central table for all configuration policies. "
        "Contains policy_name, policy_type, policy_description, profile_id, "
        "created_by, modified_by, customer_id. "
        "Use for: policies, policy name, policy type, all policies, who created a policy."
    ),
    "policy_patch_mapping": (
        "Table 'policy_patch_mapping' maps patches to patch deployment policies. "
        "Use for: which patches are in which deployment policy."
    ),
    "power_management_policy": (
        "Table 'power_management_policy' defines power plan settings for managed devices. "
        "Contains policy_id, sleep_after_ac, sleep_after_battery, display_off_ac, "
        "display_off_battery, hibernate_after_ac, fast_startup_enabled, require_password_on_wake. "
        "Use for: power management, sleep settings, display timeout, hibernate settings, power plan."
    ),
    "pre_post_check": (
        "Table 'pre_post_check' groups pre/post deployment checks together. "
        "Contains references to disk_space, file_folder, registry, service, software checks. "
        "Use for: deployment pre-checks, post-installation checks, deployment validation."
    ),
    "pre_post_check_disk_space": (
        "Table 'pre_post_check_disk_space' checks if sufficient disk space exists before deployment. "
        "Contains disk, minimum_space, is_pre_check. "
        "Use for: disk space pre-check, minimum disk requirement."
    ),
    "pre_post_check_file_folder": (
        "Table 'pre_post_check_file_folder' checks file/folder existence before/after deployment. "
        "Contains path, type, is_pre_check. "
        "Use for: file existence check, folder check, deployment condition."
    ),
    "pre_post_check_registry": (
        "Table 'pre_post_check_registry' checks Windows registry values for deployment conditions. "
        "Contains registry_name, value_name, is_pre_check. "
        "Use for: registry check, registry key condition."
    ),
    "pre_post_check_service_running": (
        "Table 'pre_post_check_service_running' checks if a Windows service is running. "
        "Contains service_name, condition, is_pre_check. "
        "Use for: service running check, service dependency check."
    ),
    "pre_post_check_software_installed": (
        "Table 'pre_post_check_software_installed' checks if software is installed as a condition. "
        "Contains software_name, condition, is_pre_check. "
        "Use for: software installed check, dependency software check."
    ),
    "pre_post_configuration": (
        "Table 'pre_post_configuration' stores pre/post deployment configuration settings. "
        "Contains proceed_on_failure, customer_id. "
        "Use for: deployment configuration, pre/post settings, failure handling."
    ),
    "pre_post_custom_script": (
        "Table 'pre_post_custom_script' runs a custom script before/after deployment. "
        "Contains script_policy_id, is_pre_configuration, config_id. "
        "Use for: pre-deployment scripts, post-deployment scripts, custom scripts in deployment."
    ),
    "pre_post_kill_process": (
        "Table 'pre_post_kill_process' kills a process before/after deployment. "
        "Contains process_name, is_pre_configuration, config_id. "
        "Use for: kill process before install, terminate process in deployment."
    ),
    "pre_post_uninstall_software": (
        "Table 'pre_post_uninstall_software' uninstalls software as part of deployment. "
        "Contains software_name, software_version, uninstall_string, config_id. "
        "Use for: uninstall before install, software removal in deployment."
    ),
    "preferences": (
        "Table 'preferences' stores remote control session preferences. "
        "Contains clipboard_restriction, idle_session_timeout, idle_session_timeout_action, "
        "open_viewer_in, disable_clipboard, customer_id. "
        "Use for: remote session preferences, clipboard settings, idle timeout."
    ),
    "printer_details": (
        "Table 'printer_details' stores detailed printer hardware inventory. "
        "Contains driver_name, port_name, printer_status, location, share_name, "
        "horizontal_resolution, vertical_resolution, asset_id. "
        "Use for: printers, printer model, printer status, shared printers, printer driver."
    ),
    "processor_details": (
        "Table 'processor_details' stores CPU hardware details. "
        "Contains asset_id, clock_speed, no_of_cores, family, processor_type, "
        "hyper_threading, socket_designation, version, status. "
        "Use for: CPU cores, clock speed, processor family, hyper-threading, processor version."
    ),
    "profiles": (
        "Table 'profiles' stores configuration profiles that group policies together. "
        "Contains profile_name, profile_type, platform, profile_description, "
        "publication_status, execution_status, created_by, customer_id. "
        "Use for: profiles, configuration profiles, policy profiles, profile type, platform profiles."
    ),
    "profiles_to_command_map": (
        "Table 'profiles_to_command_map' maps commands to profiles for execution. "
        "Contains profile_id, command_id, action, customer_id. "
        "Use for: profile commands, which commands run with a profile."
    ),
    "prohibited_software": (
        "Table 'prohibited_software' stores software that is banned/prohibited for customers. "
        "Contains software_id, status, customer_id. "
        "Use for: prohibited software, banned software, blocked applications, prohibited status."
    ),
    "registry_entry": (
        "Table 'registry_entry' stores Windows registry entries to configure via policy. "
        "Contains action, header_key, sub_key, value_name, value_data, data_type, registry_policy_id. "
        "Use for: registry entries, registry keys to set, registry policy values."
    ),
    "registry_policy": (
        "Table 'registry_policy' defines registry configuration policies. "
        "Contains registry_configuration, network_path, import_source, policy_id. "
        "Use for: registry policy, Windows registry management policy."
    ),
    "relay_server": (
        "Table 'relay_server' stores relay server instances for remote session routing. "
        "Contains domain, port, ssl_enabled, live_clients, live_sessions. "
        "Use for: relay servers, remote session routing, active sessions on server."
    ),
    "report": (
        "Table 'report' stores report templates and configurations. "
        "Contains name, description, template_type, api_endpoint, favorite, "
        "created_by, type_id, customer_id. "
        "Use for: reports, report name, report type, favorite reports."
    ),
    "reports_category": (
        "Table 'reports_category' stores report categories. "
        "Contains category. "
        "Use for: report categories."
    ),
    "reports_type": (
        "Table 'reports_type' stores report types linked to categories. "
        "Contains type, category_id. "
        "Use for: report type, report category mapping."
    ),
    "roles": (
        "Table 'roles' stores customer-level user roles (Admin, Viewer, Technician etc). "
        "Contains role_name, description, is_editable, customer_id, zecure_org_id. "
        "Use for: user roles, role names, customer roles, admin role, technician role."
    ),
    "scan_status": (
        "Table 'scan_status' stores device scan job status and timing. "
        "Contains device_id, scan_type, status, initiated_time, reported_time, customer_id. "
        "Use for: scan status, scan type, scan timing, failed scans, scan history."
    ),
    "scheduled_jobs": (
        "Table 'scheduled_jobs' stores scheduled automation job configurations. "
        "Contains scheduled_job_name, scheduled_job_type, expression (cron), "
        "active_status, start_date, time_zone, user_id, customer_id. "
        "Use for: scheduled jobs, cron jobs, automation schedules, job status."
    ),
    "scheduled_notification": (
        "Table 'scheduled_notification' stores scheduled report delivery notifications. "
        "Contains email, delivery_status, scheduled_job_id, sent_time, customer_id. "
        "Use for: scheduled notifications, report delivery, email delivery status."
    ),
    "scheduled_power_option_policies": (
        "Table 'scheduled_power_option_policies' defines scheduled power actions on devices. "
        "Contains given_name, power_option, frequency, policy_id, customer_id. "
        "Use for: power schedule, scheduled shutdown, scheduled sleep, wake schedule."
    ),
    "scheduled_report": (
        "Table 'scheduled_report' stores scheduled automatic report generation tasks. "
        "Contains report_ids, schedule_id, scheduled_by, status, customer_id. "
        "Use for: scheduled reports, automated reports, report schedule."
    ),
    "scheduled_wake_on_lan_policies": (
        "Table 'scheduled_wake_on_lan_policies' defines scheduled Wake-on-LAN operations. "
        "Contains given_name, frequency, udp_port, retry_count, policy_id, customer_id. "
        "Use for: Wake-on-LAN schedule, WOL policy, scheduled device wake."
    ),
    "script_associations": (
        "Table 'script_associations' associates scripts with devices or groups. "
        "Contains script_policy_id, associated_entity_id, script_association_type, customer_id. "
        "Use for: script assignments, which devices or groups have scripts associated."
    ),
    "script_deployment_policy": (
        "Table 'script_deployment_policy' defines how scripts are deployed to devices. "
        "Contains policy_id, script_id, deployment_mode, run_the_script_as, "
        "retry_count, notify_on_success, notify_on_failure, schedule_jobs_id. "
        "Use for: script deployment policy, how scripts run, script execution settings."
    ),
    "script_policy": (
        "Table 'script_policy' stores script content and configuration. "
        "Contains script_name, script_type, platform, description, arguments, "
        "exit_codes, created_by, customer_id. "
        "Use for: scripts, script name, script type, PowerShell scripts, Bash scripts, platform scripts."
    ),
    "script_policy_tags_map": (
        "Table 'script_policy_tags_map' maps tags to script policies. "
        "Use for: script tags, tagged scripts."
    ),
    "script_tags": (
        "Table 'script_tags' stores tags for categorizing scripts. "
        "Contains tag_name, zecure_org_id. "
        "Use for: script tags, script categories."
    ),
    "script_templates": (
        "Table 'script_templates' stores reusable script templates. "
        "Contains script_name, script_type, platform, description, arguments. "
        "Use for: script templates, reusable scripts, script library."
    ),
    "script_templates_tags_map": (
        "Table 'script_templates_tags_map' maps tags to script templates. "
        "Use for: template tags, tagged templates."
    ),
    "serial_port_details": (
        "Table 'serial_port_details' stores serial port hardware info. "
        "Contains asset_id, max_baud_rate, status, is_binary_data_transferred. "
        "Use for: serial ports, COM ports, serial hardware."
    ),
    "session": (
        "Table 'session' stores remote support and access session records. "
        "Contains managed_device_id, session_type, session_status, duration, "
        "name, environment, last_active_time, customer_id. "
        "Use for: remote sessions, session type, session status, session duration, active sessions."
    ),
    "share_permissions": (
        "Table 'share_permissions' stores permissions on network shares. "
        "Contains share_name, share_user_name, full_control, read, write, customer_id. "
        "Use for: share permissions, read/write access, network share access control."
    ),
    "smetering_aggregate_org_summary": (
        "Table 'smetering_aggregate_org_summary' stores aggregated software metering totals per org. "
        "Contains software_name, file_name, total_device_count, total_run_count, "
        "total_run_duration, total_user_count, rule_id, customer_id. "
        "Use for: software metering totals, how many devices use software, total usage count."
    ),
    "smetering_daily_summary": (
        "Table 'smetering_daily_summary' stores daily software usage summary per device and user. "
        "Contains managed_device_id, software_name, user_name, host_name, "
        "total_run_count, total_run_duration, created_date. "
        "Use for: daily software usage, software run count per day, who used software on which device."
    ),
    "smetering_device_summary": (
        "Table 'smetering_device_summary' stores per-device software usage aggregates. "
        "Contains managed_device_id, software_name, user_name, total_run_count, total_run_duration. "
        "Use for: software usage per device, how long software ran on each device."
    ),
    "smetering_software_daily_summary": (
        "Table 'smetering_software_daily_summary' stores daily software usage across all devices. "
        "Contains software_name, file_name, total_run_count, total_run_duration, created_date. "
        "Use for: software daily usage totals, software popularity by day."
    ),
    "smetering_usage_raw": (
        "Table 'smetering_usage_raw' stores raw software metering event data. "
        "Contains managed_device_id, software_name, file_name, user_name, host_name, "
        "start_date, end_date, active_duration, session_date. "
        "Use for: raw software usage events, software sessions, usage duration, who ran what software."
    ),
    "software": (
        "Table 'software' stores all software products tracked in the system. "
        "Contains name, platform, manufacturer_name, software_category_name, latest_version, "
        "software_type, software_category_id, software_group_id, manufacturer_id, customer_id. "
        "Use for: software list, installed software, software name, manufacturer, platform, "
        "software category, latest version, software type."
    ),
    "software_category": (
        "Table 'software_category' stores categories for classifying software. "
        "Contains category_name, description, os_type, customer_id. "
        "Use for: software category, software type classification, OS category."
    ),
    "software_deployment_policy": (
        "Table 'software_deployment_policy' defines how software packages are deployed. "
        "Contains policy_id, package_id, deployment_mode, is_uninstall, retry_count, "
        "run_the_script_as, schedule_jobs_id, customer_id. "
        "Use for: software deployment policy, install/uninstall policy, deployment schedule."
    ),
    "software_group": (
        "Table 'software_group' groups software under a common name across versions. "
        "Contains software_name, version_count, customer_id. "
        "Use for: software groups, software families, version grouping."
    ),
    "software_metering_rule": (
        "Table 'software_metering_rule' defines rules for tracking software usage. "
        "Contains rule_name, software_name, file_name, match_type, enabled, policy_id, customer_id. "
        "Use for: software metering rules, usage tracking rules, file metering."
    ),
    "software_package": (
        "Table 'software_package' stores software installer packages for deployment. "
        "Contains package_name, platform, installer_type, source_url, install_arguments, "
        "silent_install_switch, uninstall_command, software_version_id, policy_id, customer_id. "
        "Use for: software packages, installers, deployment packages, silent install, uninstall command."
    ),
    "software_template": (
        "Table 'software_template' stores reusable software deployment templates. "
        "Contains software_name, platform, installer_type, source_url, install_arguments, "
        "operating_system, software_version_id. "
        "Use for: software templates, deployment templates, reusable install configs."
    ),
    "software_usage_settings": (
        "Table 'software_usage_settings' stores thresholds for classifying software usage frequency. "
        "Contains frequent_run_count_threshold, occasional_run_count_threshold_from, "
        "rare_run_count_threshold, customer_id. "
        "Use for: usage frequency settings, frequent/occasional/rare thresholds."
    ),
    "software_version": (
        "Table 'software_version' stores individual version entries for each software. "
        "Contains software_id, version_name, version_code, prohibited_status, "
        "windows_uninstall_string, customer_id. "
        "Use for: software versions, version name, prohibited version, uninstall string."
    ),
    "software_version_managed_device": (
        "Table 'software_version_managed_device' records which software version is installed on which device. "
        "Contains software_version_id, managed_device_id, installed_date, status, source, customer_id. "
        "Use for: installed software per device, software installation status, when software was installed, "
        "most installed software, top software, software deployment count."
    ),
    "sound_device_details": (
        "Table 'sound_device_details' stores audio hardware details. "
        "Contains product_name, description, status, asset_id. "
        "Use for: sound card, audio device, audio hardware."
    ),
    "subscription_history": (
        "Table 'subscription_history' tracks subscription plan changes over time. "
        "Contains subscription_id, old_plan_id, new_plan_id, change_type, device_count, "
        "technician_count, payment_status, effective_start_date, effective_end_date. "
        "Use for: subscription changes, plan upgrades, plan downgrades, device count history."
    ),
    "subscriptions": (
        "Table 'subscriptions' stores active and past customer subscriptions. "
        "Contains customer_id, plan_id, status, start_date, end_date, "
        "purchased_devices, purchased_technicians, auto_renew, currency_code, "
        "next_renewal_date, last_renewal_date, zecure_org_id. "
        "Use for: subscriptions, active subscription, subscription status, purchased devices, "
        "renewal date, how many devices subscribed."
    ),
    "summary_metrics_trend": (
        "Table 'summary_metrics_trend' stores trend data for dashboard metrics. "
        "Contains summary_entity_id, summary_entity_type, trend_data, customer_id. "
        "Use for: dashboard trends, metric trends, historical summary data."
    ),
    "system_scheduler": (
        "Table 'system_scheduler' stores internal system-level scheduled jobs. "
        "Contains scheduled_job_name, scheduled_job_type, expression, active_status, "
        "triggered_time, completed_time, error_message. "
        "Use for: system jobs, background jobs, job errors, job completion."
    ),
    "target": (
        "Table 'target' stores deployment/policy targets (all devices, specific group, custom). "
        "Contains name, type, customer_id. "
        "Use for: policy targets, deployment targets, target type, target name."
    ),
    "target_device_mapping": (
        "Table 'target_device_mapping' maps specific devices to a target. "
        "Contains target_id, device_id, customer_id. "
        "Use for: specific devices in a target, target device list."
    ),
    "target_group_mapping": (
        "Table 'target_group_mapping' maps device groups to a target. "
        "Contains target_id, group_id, customer_id. "
        "Use for: groups in a target, target group list."
    ),
    "technician_pricing": (
        "Table 'technician_pricing' stores pricing for technician seat count ranges. "
        "Contains min_technician, max_technician, monthly_price, yearly_price, product_id. "
        "Use for: technician pricing, pricing per technician range."
    ),
    "tpmdetails": (
        "Table 'tpmdetails' stores TPM (Trusted Platform Module) chip details. "
        "Contains asset_id, tpmowned, is_activated, is_enabled, manufacturer_name, "
        "manufacturer_version, specification_version. "
        "Use for: TPM chip, TPM status, TPM version, security chip."
    ),
    "usb_controller_details": (
        "Table 'usb_controller_details' stores USB controller hardware info. "
        "Contains asset_id, pnpdevice_id, status. "
        "Use for: USB controller, USB hardware status."
    ),
    "usb_hub_details": (
        "Table 'usb_hub_details' stores USB hub hardware details. "
        "Contains asset_id, description, serial_number, type, status. "
        "Use for: USB hubs, USB hub type, USB device details."
    ),
    "user_confirmation_exclusion": (
        "Table 'user_confirmation_exclusion' stores groups excluded from user confirmation prompts. "
        "Contains zecure_group_id, customer_id. "
        "Use for: excluded groups from confirmation, silent operation groups."
    ),
    "user_logon_history": (
        "Table 'user_logon_history' stores user login and logoff event history. "
        "Contains managed_user_id, device_id, logon_time, logoff_time, logon_type, "
        "logon_method, ip_address, event_status, geo_location, mac_address, customer_id. "
        "Use for: login history, logon events, logoff time, login IP, login type, "
        "who logged in, last login, failed logins, login duration."
    ),
    "user_management_policy": (
        "Table 'user_management_policy' defines policies for managing local user accounts on devices. "
        "Contains username, user_action, account_status, password, groups_to_add, "
        "force_password_change_at_first_login, policy_id. "
        "Use for: user management policy, create user, delete user, local account policy."
    ),
    "user_subscriptions": (
        "Table 'user_subscriptions' maps users to their subscriptions. "
        "Contains customer_id, org_member_id, subscription_id, product_id, user_id. "
        "Use for: user subscription mapping, which users have subscriptions."
    ),
    "video_controller_details": (
        "Table 'video_controller_details' stores GPU/graphics card hardware details. "
        "Contains asset_id, description, driver_version, adapter_ram, "
        "horizontal_resolution, vertical_resolution, current_bits_per_pixel. "
        "Use for: GPU details, graphics card, video adapter, screen resolution, adapter RAM."
    ),
    "wake_on_lan_settings": (
        "Table 'wake_on_lan_settings' stores Wake-on-LAN configuration per customer. "
        "Contains port, retry_count, retry_interval, status_check_interval, customer_id. "
        "Use for: Wake-on-LAN settings, WOL port, WOL configuration."
    ),
    "windows_update_policy": (
        "Table 'windows_update_policy' defines Windows Update configuration policies. "
        "Contains policy_id, automatic_update_mode, defer_quality_updates_days, "
        "defer_feature_updates_days, scheduled_install_day, scheduled_install_time, "
        "allow_pause_updates, include_driver_updates, use_wsus_server, wsus_server_url. "
        "Use for: Windows Update policy, defer updates, automatic updates, WSUS configuration, "
        "scheduled updates."
    ),
    "zecure_group": (
        "Table 'zecure_group' stores device groups for targeting policies and deployments. "
        "Contains group_name, group_type, entity_type, creation_type, description, "
        "count, status, owner_id, customer_id. "
        "Use for: device groups, group name, group type, dynamic groups, static groups, "
        "how many devices in a group."
    ),
    "zecure_group_dynamic_group_criterias": (
        "Table 'zecure_group_dynamic_group_criterias' maps dynamic group criteria to groups. "
        "Use for: which criteria apply to which dynamic group."
    ),
    "zecure_group_managed_devices": (
        "Table 'zecure_group_managed_devices' maps managed devices to their groups. "
        "Contains managed_device_id, zecure_group_id, customer_id. "
        "Use for: devices in a group, group members, which group a device belongs to."
    ),
    "zecure_group_members": (
        "Table 'zecure_group_members' maps technician/user org members to groups. "
        "Contains org_members_id, zecure_group_id, zecure_org_id. "
        "Use for: user group membership, which users are in a group."
    ),
}


def fetch_schema_descriptions() -> list[dict]:
    """Kept for backward compatibility with any external callers — now backed
    by schema_introspect instead of a raw information_schema query, so
    descriptions are auto-synthesized (DB comments / FK relationships) for
    any table not covered by RICH_DESCRIPTIONS, instead of a bare column list."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set in .env"); sys.exit(1)
    return introspect_all(DATABASE_URL, RICH_DESCRIPTIONS)


def _get_collection(client):
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        return client.create_collection(COLLECTION_NAME)


def build_index(incremental: bool = True) -> dict:
    """
    incremental=True (default): only re-embeds tables whose content_hash
    changed since the last run (new tables, altered columns/comments/FKs),
    and removes entries for tables that no longer exist. This is what makes
    it safe to run regularly/automatically against a cloud DB that changes
    on its own schedule — a full 234-table re-embed on every schema tweak
    doesn't scale.

    incremental=False: wipes and rebuilds the whole collection from scratch
    (the original behavior) — use for a first-time build or if you suspect
    the index itself is corrupted.

    Returns a summary dict: {added, updated, removed, unchanged, sources}.
    """
    print(f"Loading embedding model '{EMBED_MODEL}'...")
    model = SentenceTransformer(EMBED_MODEL)

    print("Introspecting live schema (columns, DB comments, foreign keys)...")
    tables = fetch_schema_descriptions()
    print(f"Found {len(tables)} tables")
    sources = {"manual": 0, "db_comment": 0, "auto": 0}
    for t in tables:
        sources[t.get("source", "manual")] = sources.get(t.get("source", "manual"), 0) + 1
    print(f"  Sources — manual: {sources['manual']}, DB comment: {sources['db_comment']}, auto-generated: {sources['auto']}")

    print(f"Initializing ChromaDB at '{CHROMA_DB_PATH}'...")
    os.makedirs(CHROMA_DB_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    if not incremental:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        collection = client.create_collection(COLLECTION_NAME)
        existing_hashes = {}
    else:
        collection = _get_collection(client)
        existing = collection.get(include=["metadatas"])
        existing_hashes = {
            tid: (meta or {}).get("content_hash")
            for tid, meta in zip(existing["ids"], existing["metadatas"])
        }

    current_names = {t["table_name"] for t in tables}
    to_upsert = [t for t in tables if existing_hashes.get(t["table_name"]) != t["content_hash"]]
    to_remove = [tid for tid in existing_hashes if tid not in current_names]
    unchanged = len(tables) - len(to_upsert)

    if to_remove:
        collection.delete(ids=to_remove)
        print(f"Removed {len(to_remove)} table(s) no longer in the schema: {to_remove}")

    if to_upsert:
        print(f"Embedding {len(to_upsert)} new/changed table description(s) ({unchanged} unchanged, skipped)...")
        texts = [t["description"] for t in to_upsert]
        embeddings = model.encode(texts, show_progress_bar=True).tolist()
        collection.upsert(
            ids=[t["table_name"] for t in to_upsert],
            embeddings=embeddings,
            documents=[t["description"] for t in to_upsert],
            metadatas=[{
                "table_name": t["table_name"], "raw_ddl": t["raw_ddl"],
                "content_hash": t["content_hash"], "source": t.get("source", "manual"),
            } for t in to_upsert],
        )
    else:
        print("No schema changes detected — nothing to re-embed.")

    added = len([t for t in to_upsert if t["table_name"] not in existing_hashes])
    updated = len(to_upsert) - added
    summary = {"added": added, "updated": updated, "removed": len(to_remove),
               "unchanged": unchanged, "total_tables": len(tables), "sources": sources}
    print(f"\n✅ Index sync complete — {added} added, {updated} updated, {len(to_remove)} removed, {unchanged} unchanged.")
    print(f"   Storage: {CHROMA_DB_PATH}")
    return summary


if __name__ == "__main__":
    full_rebuild = "--full" in sys.argv
    build_index(incremental=not full_rebuild)
