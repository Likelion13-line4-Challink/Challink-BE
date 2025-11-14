# settlements/admin.py
from django.contrib import admin
from .models import Settlement, SettlementDetail


# ✅ SettlementDetail 인라인 (정산 상세 내역)
class SettlementDetailInline(admin.TabularInline):
    model = SettlementDetail
    extra = 0
    readonly_fields = ("challenge_member", "reward_point", "claimed_at", "created_at")
    autocomplete_fields = ("challenge_member",)
    can_delete = False


# ✅ Settlement (정산 본체)
@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = (
        "settlement_id",
        "challenge",
        "method",
        "status",
        "total_pool_point",
        "scheduled_at",
        "settled_at",
        "created_at",
    )
    list_filter = ("status", "method", "scheduled_at")
    search_fields = ("challenge__title",)
    ordering = ("-scheduled_at",)
    readonly_fields = ("created_at", "settled_at")
    autocomplete_fields = ("challenge",)
    inlines = [SettlementDetailInline]

    fieldsets = (
        ("기본 정보", {
            "fields": ("challenge", "method", "total_pool_point")
        }),
        ("진행 상태", {
            "fields": ("status", "scheduled_at", "settled_at")
        }),
        ("기타", {
            "fields": ("created_at",)
        }),
    )


# ✅ SettlementDetail (단독 관리용)
@admin.register(SettlementDetail)
class SettlementDetailAdmin(admin.ModelAdmin):
    list_display = (
        "detail_id",
        "settlement",
        "challenge_member",
        "reward_point",
        "claimed_at",
        "created_at",
    )
    list_filter = ("claimed_at",)
    search_fields = ("settlement__challenge__title", "challenge_member__user__email")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("settlement", "challenge_member")


# ✅ 관리자 페이지 공통 헤더
admin.site.site_header = "Challink Admin"
admin.site.site_title = "Challink Admin"
admin.site.index_title = "정산 관리"
