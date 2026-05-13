# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
business/middleware.py — Rate limiting and usage tracking middleware.

Implements tier-based API rate limiting and usage logging.
"""
import time
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

from business.models import Organization, UsageLog


class RateLimitMiddleware:
    """
    Rate limit API requests based on organization tier.
    
    Limits:
    - Academic: 0 API calls/day (no API access)
    - Professional: 1000 API calls/day
    - Business: 5000 API calls/day
    - Enterprise: Unlimited
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Only apply to API endpoints
        if not request.path.startswith('/api/'):
            return self.get_response(request)
        
        # Skip rate limiting for unauthenticated requests (public endpoints)
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Get user's organization
        try:
            profile = request.user.profile
            organization = profile.organization
        except:
            # No profile/organization — allow request
            return self.get_response(request)
        
        # Check if subscription is active
        if not organization.is_subscription_active:
            return JsonResponse({
                "error": "Subscription expired",
                "message": "Your subscription has expired. Please renew to continue using the API.",
                "organization": organization.name,
                "tier": organization.get_tier_display(),
            }, status=402)  # Payment Required
        
        # Get rate limit for tier
        daily_limit = organization.api_calls_per_day
        
        # Academic tier has no API access
        if daily_limit == 0:
            return JsonResponse({
                "error": "API access not available",
                "message": "API access is not available on the Academic tier. Upgrade to Professional or higher.",
                "tier": organization.get_tier_display(),
                "upgrade_url": "/pricing/",
            }, status=403)  # Forbidden
        
        # Enterprise tier is unlimited
        if daily_limit >= 999999:
            return self.get_response(request)
        
        # Check rate limit using Redis cache
        cache_key = f"api_rate_limit:{organization.id}:{timezone.now().date()}"
        current_count = cache.get(cache_key, 0)
        
        if current_count >= daily_limit:
            return JsonResponse({
                "error": "Rate limit exceeded",
                "message": f"You have exceeded your daily API limit of {daily_limit} calls.",
                "limit": daily_limit,
                "used": current_count,
                "reset_at": f"{timezone.now().date() + timezone.timedelta(days=1)} 00:00 UTC",
                "tier": organization.get_tier_display(),
                "upgrade_url": "/pricing/",
            }, status=429)  # Too Many Requests
        
        # Increment counter
        cache.set(cache_key, current_count + 1, timeout=86400)  # 24 hours
        
        # Process request
        start_time = time.time()
        response = self.get_response(request)
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Log usage asynchronously (don't block response)
        try:
            UsageLog.objects.create(
                organization=organization,
                user=request.user,
                action_type=UsageLog.ActionType.API_CALL,
                endpoint=request.path,
                response_time_ms=response_time_ms,
            )
        except:
            pass  # Don't fail request if logging fails
        
        # Add rate limit headers to response
        response['X-RateLimit-Limit'] = str(daily_limit)
        response['X-RateLimit-Remaining'] = str(max(0, daily_limit - current_count - 1))
        response['X-RateLimit-Reset'] = f"{timezone.now().date() + timezone.timedelta(days=1)} 00:00 UTC"
        
        return response


class UsageTrackingMiddleware:
    """
    Track bond views and exports for billing purposes.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Only track for authenticated users
        if not request.user.is_authenticated:
            return response
        
        # Get user's organization
        try:
            profile = request.user.profile
            organization = profile.organization
        except:
            return response
        
        # Track bond detail views
        if request.path.startswith('/bond/') and request.method == 'GET':
            bond_id = request.path.split('/')[2]
            try:
                UsageLog.objects.create(
                    organization=organization,
                    user=request.user,
                    action_type=UsageLog.ActionType.BOND_VIEW,
                    bond_id=bond_id,
                )
            except:
                pass
        
        # Track CSV exports
        if '/export/' in request.path and request.method == 'GET':
            try:
                UsageLog.objects.create(
                    organization=organization,
                    user=request.user,
                    action_type=UsageLog.ActionType.CSV_EXPORT,
                    endpoint=request.path,
                )
            except:
                pass
        
        return response


class FeatureAccessMiddleware:
    """
    Check feature access based on organization tier.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Only check for authenticated users
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Get user's organization
        try:
            profile = request.user.profile
            organization = profile.organization
        except:
            return self.get_response(request)
        
        # Check feature access for specific endpoints
        restricted_endpoints = {
            '/export/': 'csv_export',
            '/api/': 'api_access',
            '/portfolio/': 'portfolio_analysis',
        }
        
        for endpoint_prefix, feature_key in restricted_endpoints.items():
            if request.path.startswith(endpoint_prefix):
                if not organization.features.get(feature_key, False):
                    return JsonResponse({
                        "error": "Feature not available",
                        "message": f"This feature is not available on the {organization.get_tier_display()} tier.",
                        "feature": feature_key,
                        "tier": organization.get_tier_display(),
                        "upgrade_url": "/pricing/",
                    }, status=403)
        
        return self.get_response(request)
