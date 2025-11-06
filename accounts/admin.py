# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Profile, PointHistory


# ✅ Profile 관리자 설정
@admin.register(Profile)
class ProfileAdmin(BaseUserAdmin):
    list_display = ("id", "email", "name", "point_balance", "is_active", "is_staff", "created_at")
    list_display_links = ("email",)
    list_filter = ("is_active", "is_staff", "created_at")
    search_fields = ("email", "name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("기본 정보", {
            "fields": ("email", "name", "password")
        }),
        ("권한 정보", {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        ("포인트 정보", {
            "fields": ("point_balance",)
        }),
        ("기타", {
            "fields": ("created_at", "updated_at")
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "name", "password1", "password2", "is_staff", "is_active"),
        }),
    )


# ✅ PointHistory 관리자 설정
@admin.register(PointHistory)
class PointHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "point_history_id",
        "user",
        "challenge",
        "type",
        "amount",
        "balance_after",
        "description",
        "occurred_at",
    )
    list_filter = ("type", "occurred_at")
    search_fields = ("user__email", "description", "challenge__title")
    ordering = ("-occurred_at",)
    readonly_fields = ("occurred_at", "created_at")

    autocomplete_fields = ("user", "challenge")  # ForeignKey 검색 편하게


# ✅ 관리자 페이지에서 더 깔끔하게 보이도록
admin.site.site_header = "Challink Admin"
admin.site.site_title = "Challink Admin"
admin.site.index_title = "관리자 페이지"
