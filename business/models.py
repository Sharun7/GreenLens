# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
business/models.py — Subscription, Licensing, and Usage Tracking Models

Implements tiered SaaS pricing model for GreenLens:
- Tier 0: Academic (Free)
- Tier 1: Professional (€299/month)
- Tier 2: Business (€1,499/month)
- Tier 3: Enterprise (€4,999/month)
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta


class SubscriptionTier(models.TextChoices):
    """Subscription tier levels."""
    ACADEMIC = "academic", "Academic (Free)"
    PROFESSIONAL = "professional", "Professional"
    BUSINESS = "business", "Business"
    ENTERPRISE = "enterprise", "Enterprise"


class Organization(models.Model):
    """
    Organization/Company using GreenLens.
    
    Each organization has a subscription tier and usage limits.
    """
    
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    
    # Subscription
    tier = models.CharField(
        max_length=20,
        choices=SubscriptionTier.choices,
        default=SubscriptionTier.ACADEMIC,
        db_index=True,
    )
    
    # Billing
    subscription_start_date = models.DateField(null=True, blank=True)
    subscription_end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Contact
    billing_email = models.EmailField()
    contact_name = models.CharField(max_length=255)
    contact_phone = models.CharField(max_length=50, blank=True)
    
    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    
    # Enterprise features
    white_label_enabled = models.BooleanField(default=False)
    custom_branding_logo = models.URLField(blank=True)
    dedicated_account_manager = models.CharField(max_length=255, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tier", "is_active"]),
            models.Index(fields=["subscription_end_date"]),
        ]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
    
    def __str__(self):
        return f"{self.name} ({self.get_tier_display()})"
    
    @property
    def is_subscription_active(self) -> bool:
        """Check if subscription is currently active."""
        if not self.is_active:
            return False
        if self.tier == SubscriptionTier.ACADEMIC:
            return True  # Academic is always active
        if not self.subscription_end_date:
            return False
        return self.subscription_end_date >= timezone.now().date()
    
    @property
    def days_until_expiry(self) -> int:
        """Days until subscription expires."""
        if not self.subscription_end_date:
            return 0
        delta = self.subscription_end_date - timezone.now().date()
        return max(0, delta.days)
    
    @property
    def monthly_price_eur(self) -> int:
        """Monthly subscription price in EUR."""
        prices = {
            SubscriptionTier.ACADEMIC: 0,
            SubscriptionTier.PROFESSIONAL: 299,
            SubscriptionTier.BUSINESS: 1499,
            SubscriptionTier.ENTERPRISE: 4999,
        }
        return prices.get(self.tier, 0)
    
    @property
    def max_users(self) -> int:
        """Maximum users allowed for this tier."""
        limits = {
            SubscriptionTier.ACADEMIC: 1,
            SubscriptionTier.PROFESSIONAL: 5,
            SubscriptionTier.BUSINESS: 25,
            SubscriptionTier.ENTERPRISE: 999999,  # Unlimited
        }
        return limits.get(self.tier, 1)
    
    @property
    def max_bonds_per_month(self) -> int:
        """Maximum bonds viewable per month."""
        limits = {
            SubscriptionTier.ACADEMIC: 100,
            SubscriptionTier.PROFESSIONAL: 999999,  # Unlimited
            SubscriptionTier.BUSINESS: 999999,
            SubscriptionTier.ENTERPRISE: 999999,
        }
        return limits.get(self.tier, 100)
    
    @property
    def api_calls_per_day(self) -> int:
        """Maximum API calls per day."""
        limits = {
            SubscriptionTier.ACADEMIC: 0,  # No API access
            SubscriptionTier.PROFESSIONAL: 1000,
            SubscriptionTier.BUSINESS: 5000,
            SubscriptionTier.ENTERPRISE: 999999,  # Unlimited
        }
        return limits.get(self.tier, 0)
    
    @property
    def features(self) -> dict:
        """Feature access by tier."""
        base_features = {
            "bond_viewing": True,
            "pcrs_scores": True,
            "greenwash_flags": True,
            "pricing_gaps": True,
            "csv_export": False,
            "api_access": False,
            "shap_breakdown": False,
            "portfolio_analysis": False,
            "custom_reports": False,
            "white_label": False,
            "on_premise": False,
            "sla_guarantee": False,
        }
        
        if self.tier == SubscriptionTier.PROFESSIONAL:
            base_features.update({
                "csv_export": True,
                "api_access": True,
                "shap_breakdown": True,
            })
        
        elif self.tier == SubscriptionTier.BUSINESS:
            base_features.update({
                "csv_export": True,
                "api_access": True,
                "shap_breakdown": True,
                "portfolio_analysis": True,
                "custom_reports": True,
            })
        
        elif self.tier == SubscriptionTier.ENTERPRISE:
            base_features.update({
                "csv_export": True,
                "api_access": True,
                "shap_breakdown": True,
                "portfolio_analysis": True,
                "custom_reports": True,
                "white_label": True,
                "on_premise": True,
                "sla_guarantee": True,
            })
        
        return base_features


class UserProfile(models.Model):
    """
    Extended user profile linked to an organization.
    """
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="users",
        db_index=True,
    )
    
    role = models.CharField(
        max_length=50,
        choices=[
            ("admin", "Administrator"),
            ("analyst", "Analyst"),
            ("viewer", "Viewer"),
        ],
        default="viewer",
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
    
    def __str__(self):
        return f"{self.user.username} @ {self.organization.name}"


class UsageLog(models.Model):
    """
    Track API usage and bond views for billing and rate limiting.
    """
    
    class ActionType(models.TextChoices):
        BOND_VIEW = "bond_view", "Bond View"
        API_CALL = "api_call", "API Call"
        CSV_EXPORT = "csv_export", "CSV Export"
        REPORT_GENERATE = "report_generate", "Report Generate"
    
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="usage_logs",
        db_index=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_logs",
    )
    
    action_type = models.CharField(
        max_length=20,
        choices=ActionType.choices,
        db_index=True,
    )
    
    # Details
    endpoint = models.CharField(max_length=255, blank=True)
    bond_id = models.CharField(max_length=100, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["organization", "timestamp"]),
            models.Index(fields=["organization", "action_type", "timestamp"]),
        ]
        verbose_name = "Usage Log"
        verbose_name_plural = "Usage Logs"
    
    def __str__(self):
        return f"{self.organization.name} - {self.action_type} @ {self.timestamp}"


class Invoice(models.Model):
    """
    Invoice for subscription billing.
    """
    
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"
    
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invoices",
        db_index=True,
    )
    
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    
    # Billing period
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Amount
    amount_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, default="EUR")
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    
    # Dates
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    
    # Payment
    payment_method = models.CharField(max_length=50, blank=True)
    transaction_id = models.CharField(max_length=255, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ["-issue_date"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["due_date"]),
        ]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
    
    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.organization.name}"
    
    @property
    def is_overdue(self) -> bool:
        """Check if invoice is overdue."""
        if self.status == self.Status.PAID:
            return False
        return self.due_date < timezone.now().date()


class Feature(models.Model):
    """
    Feature flags for gradual rollout and A/B testing.
    """
    
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField()
    
    # Availability
    enabled_for_tiers = models.JSONField(
        default=list,
        help_text="List of tier slugs this feature is enabled for",
    )
    
    # Rollout
    is_beta = models.BooleanField(default=False)
    rollout_percentage = models.IntegerField(
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of users who see this feature (0-100)",
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name"]
        verbose_name = "Feature"
        verbose_name_plural = "Features"
    
    def __str__(self):
        return self.name
    
    def is_enabled_for_organization(self, organization: Organization) -> bool:
        """Check if feature is enabled for given organization."""
        if not self.enabled_for_tiers:
            return False
        return organization.tier in self.enabled_for_tiers
