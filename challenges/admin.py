# challenges/admin.py
from django.contrib import admin
from .models import *


# ✅ 카테고리
@admin.register(ChallengeCategory)
class ChallengeCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    ordering = ("id",)


# ✅ 챌린지 멤버 인라인 (챌린지 상세에서 보기용)
class ChallengeMemberInline(admin.TabularInline):
    model = ChallengeMember
    extra = 0
    readonly_fields = ("user", "joined_at", "success_rate", "final_points_awarded", "final_rank")
    autocomplete_fields = ("user",)
    can_delete = False


# ✅ 챌린지
@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "category",
        "owner",
        "entry_fee",
        "duration_weeks",
        "freq_type",
        "member_count_cache",
        "start_date",
        "end_date",
    )
    list_filter = ("status", "freq_type", "category", "start_date")
    search_fields = ("title", "owner__email", "category__name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("category", "owner")
    inlines = [ChallengeMemberInline]

    fieldsets = (
        ("기본 정보", {
            "fields": ("title", "subtitle", "cover_image", "category", "owner")
        }),
        ("챌린지 설정", {
            "fields": ("entry_fee", "duration_weeks", "freq_type", "freq_n_days", "ai_condition", "settle_method")
        }),
        ("진행 상태", {
            "fields": ("status", "start_date", "end_date", "member_limit", "member_count_cache")
        }),
        ("기타", {
            "fields": ("created_at", "updated_at")
        }),
    )


# ✅ 챌린지 멤버
@admin.register(ChallengeMember)
class ChallengeMemberAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "challenge",
        "user",
        "role",
        "success_rate",
        "final_points_awarded",
        "final_rank",
        "joined_at",
    )
    list_filter = ("role", "joined_at")
    search_fields = ("user__email", "challenge__title")
    ordering = ("-joined_at",)
    autocomplete_fields = ("challenge", "user")
    readonly_fields = ("joined_at", "ended_at")


# ✅ 인증 이미지
class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    readonly_fields = ("user", "content", "x_ratio", "y_ratio", "created_at")
    can_delete = False


@admin.register(CompleteImage)
class CompleteImageAdmin(admin.ModelAdmin):
    list_display = ("id", "challenge_member", "user", "status", "date", "comment_count", "created_at")
    list_filter = ("status", "date", "created_at")
    search_fields = ("user__email", "challenge_member__challenge__title")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("challenge_member", "user")
    inlines = [CommentInline]


# ✅ 댓글
@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "complete_image", "user", "content", "created_at", "is_deleted")
    list_filter = ("is_deleted", "created_at")
    search_fields = ("user__email", "content")
    ordering = ("-created_at",)
    autocomplete_fields = ("complete_image", "user")
    readonly_fields = ("created_at",)


# ✅ 초대 코드
@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ("id", "challenge", "code", "is_used", "usage_count", "expires_at", "created_at")
    list_filter = ("is_used", "expires_at")
    search_fields = ("code", "challenge__title")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("challenge",)


# ✅ 관리자 페이지 타이틀 통일
admin.site.site_header = "Challink Admin"
admin.site.site_title = "Challink Admin"
admin.site.index_title = "Challink 관리"
