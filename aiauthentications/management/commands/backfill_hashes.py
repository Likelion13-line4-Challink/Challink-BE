from django.core.management.base import BaseCommand, CommandParser
from django.db import models
from django.utils import timezone

# 데이터는 challenges 앱의 모델을 사용
from challenges.models import CompleteImage

# 해시 유틸은 aiauthentications 쪽 것을 사용
from aiauthentications.utils.image_hashing import calc_sha1, calc_phash


class Command(BaseCommand):
    help = "Fill file_sha1 and phash for existing CompleteImage rows (backfill)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=0, help="최대 처리 건수 (0은 제한 없음)")
        parser.add_argument("--challenge", type=int, default=0, help="특정 challenge_id만 처리")
        parser.add_argument("--only-missing", action="store_true", help="해시가 비어있는 행만 처리(기본)")
        parser.add_argument("--force-recalc", action="store_true", help="기존 값이 있어도 강제 재계산")

    def handle(self, *args, **opts):
        limit = int(opts.get("limit") or 0)
        challenge_id = int(opts.get("challenge") or 0)
        only_missing = bool(opts.get("only_missing") or True)
        force_recalc = bool(opts.get("force_recalc") or False)

        qs = CompleteImage.objects.all().order_by("id")

        if challenge_id:
            qs = qs.filter(challenge_member__challenge_id=challenge_id)

        if only_missing and not force_recalc:
            qs = qs.filter(models.Q(file_sha1__isnull=True) | models.Q(phash__isnull=True))

        if limit > 0:
            qs = qs[:limit]

        processed = 0
        updated = 0
        errors = 0

        self.stdout.write(self.style.NOTICE(
            f"Start backfill: count≈{qs.count() if hasattr(qs, 'count') else 'unknown'} "
            f"(limit={limit}, challenge={challenge_id or 'ALL'}, "
            f"{'only-missing' if only_missing and not force_recalc else 'recalc-all'})"
        ))

        for ci in qs.iterator(chunk_size=200):
            try:
                changed = []

                # SHA-1
                if force_recalc or not ci.file_sha1:
                    try:
                        sha1 = calc_sha1(ci.image)
                        if sha1 and sha1 != ci.file_sha1:
                            ci.file_sha1 = sha1
                            changed.append("file_sha1")
                    except Exception as e:
                        self.stderr.write(f"[id={ci.id}] SHA-1 error: {e}")

                # pHash
                if force_recalc or not ci.phash:
                    try:
                        ph = calc_phash(ci.image)
                        if ph and ph != ci.phash:
                            ci.phash = ph
                            changed.append("phash")
                    except Exception as e:
                        self.stderr.write(f"[id={ci.id}] pHash error: {e}")

                if changed:
                    ci.save(update_fields=changed)
                    updated += 1

                processed += 1
                if processed % 200 == 0:
                    self.stdout.write(f"  processed={processed}, updated={updated}")

            except Exception as e:
                errors += 1
                self.stderr.write(f"[id={getattr(ci, 'id', '?')}] row error: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. processed={processed}, updated={updated}, errors={errors}, at={timezone.now()}"
        ))
