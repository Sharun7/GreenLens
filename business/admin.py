# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""business/admin.py — Django admin for subscription management."""
from django.contrib import admin
from django.utils.html import format_html
from .models import Organization, UserProfile, UsageLog, Invoice, Feature


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = [
        "name", "tier_badge", "is_active_badge", "subscription_end_date",
        "monthly_price_display", "user_count", "created_at"
    ]
    list_filter = ["tier", "is_active", "subscription_end_date", "created_at"]
    search_fields = ["name", "billing_email", "contact_name"]
    readonly_fields = ["created_at", "updated_at", "days_until_expiry"]
    
    fieldsets = (
        ("Organization", {
            "fields": ("name", "slug", "tier", "is_active")
        }),
        ("Subscription", {
            "fields": ("subscription_start_date", "subscription_end_date", "days_until_expiry")
        }),
        ("Contact", {
            "fields": ("billing_email", "contact_name", "contact_phone")
        }),
        ("Address", {
            "fields": ("address_line1", "address_line2", "city", "country", "postal_code"),
            "classes": ("collapse",)
        }),
        ("Enterprise Features", {
            "fields": ("white_label_enabled", "custom_branding_logo", "dedicated_account_manager"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def tier_badge(self, obj):
        colors = {
            "academic": "#6c757d",
            "professional": "#0F6E56",
            "business": "#534AB7",
            "enterprise": "#E24B4A",
        }
        color = colors.get(obj.tier, "#6c757d")
        return format_html(
            '<span style="background:{}; color:white; padding:3px 8px; border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_tier_display()
        )
    tier_badge.short_description = "Tier"
    
    def is_active_badge(self, obj):
        if obj.is_subscription_active:
            return format_html('<span style="color:green;">✓ Active</span>')
        return format_html('<span style="color:red;">✗ Expired</span>')
    is_active_badge.short_description = "Status"
    
    def monthly_price_display(self, obj):
        return f"€{obj.monthly_price_eur}"
    monthly_price_display.short_description = "Monthly Price"
    
    def user_count(self, obj):
        return obj.users.count()
    user_count.short_description = "Users"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role_badge", "created_at", "last_login_at"]
    list_filter = ["role", "organization__tier", "created_at"]
    search_fields = ["user__username", "user__email", "organization__name"]
    readonly_fields = ["created_at", "last_login_at"]
    
    fieldsets = (
        ("User", {
            "fields": ("user", "organization", "role")
        }),
        ("Activity", {
            "fields": ("created_at", "last_login_at")
        }),
    )
    
    def role_badge(self, obj):
        colors = {
            "admin": "#E24B4A",
            "analyst": "#0F6E56",
            "viewer": "#6c757d",
        }
        color = colors.get(obj.role, "#6c757d")
        return format_html(
            '<span style="background:{}; color:white; padding:3px 8px; border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_role_display()
        )
    role_badge.short_description = "Role"


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = ["organization", "user", "action_type_badge", "endpoint", "response_time_ms", "timestamp"]
    list_filter = ["action_type", "timestamp", "organization__tier"]
    search_fields = ["organization__name", "user__username", "endpoint", "bond_id"]
    readonly_fields = ["timestamp"]
    date_hierarchy = "timestamp"
    
    fieldsets = (
        ("Usage", {
            "fields": ("organization", "user", "action_type")
        }),
        ("Details", {
            "fields": ("endpoint", "bond_id", "response_time_ms")
        }),
        ("Timestamp", {
            "fields": ("timestamp",)
        }),
    )
    
    def action_type_badge(self, obj):
        colors = {
            "bond_view": "#0F6E56",
            "api_call": "#534AB7",
            "csv_export": "#E24B4A",
            "report_generate": "#EF9F27",
        }
        color = colors.get(obj.action_type, "#6c757d")
        return format_html(
            '<span style="background:{}; color:white; padding:3px 8px; border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_action_type_display()
        )
    action_type_badge.short_description = "Action"


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "invoice_number", "organization", "amount_display",
        "status_badge", "issue_date", "due_date", "paid_date"
    ]
    list_filter = ["status", "issue_date", "due_date"]
    search_fields = ["invoice_number", "organization__name", "transaction_id"]
    readonly_fields = ["issue_date", "is_overdue"]
    
    fieldsets = (
        ("Invoice", {
            "fields": ("invoice_number", "organization", "status")
        }),
        ("Billing Period", {
            "fields": ("period_start", "period_end")
        }),
        ("Amount", {
            "fields": ("amount_eur", "currency")
        }),
        ("Dates", {
            "fields": ("issue_date", "due_date", "paid_date", "is_overdue")
        }),
        ("Payment", {
            "fields": ("payment_method", "transaction_id"),
            "classes": ("collapse",)
        }),
        ("Notes", {
            "fields": ("notes",),
            "classes": ("collapse",)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            "draft": "#6c757d",
            "sent": "#534AB7",
            "paid": "#0F6E56",
            "overdue": "#E24B4A",
            "cancelled": "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{}; color:white; padding:3px 8px; border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = "Status"
    
    def amount_display(self, obj):
        return f"€{obj.amount_eur}"
    amount_display.short_description = "Amount"


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ["name", "is_beta_badge", "rollout_percentage", "enabled_tiers", "created_at"]
    list_filter = ["is_beta", "created_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at"]
    
    fieldsets = (
        ("Feature", {
            "fields": ("name", "description")
        }),
        ("Availability", {
            "fields": ("enabled_for_tiers", "is_beta", "rollout_percentage")
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def is_beta_badge(self, obj):
        if obj.is_beta:
            return format_html('<span style="background:#EF9F27; color:white; padding:3px 8px; border-radius:3px; font-size:0.85em;">BETA</span>')
        return format_html('<span style="color:green;">✓ Stable</span>')
    is_beta_badge.short_description = "Status"
    
    def enabled_tiers(self, obj):
        if not obj.enabled_for_tiers:
            return "None"
        return ", ".join(obj.enabled_for_tiers)
    enabled_tiers.short_description = "Enabled For"

