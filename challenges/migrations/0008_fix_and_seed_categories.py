from django.db import migrations

TARGET = [
    (1, "운동"),
    (2, "식습관"),
    (3, "생활"),
    (4, "기타"),
]

def forwards(apps, schema_editor):
    Category = apps.get_model("challenges", "ChallengeCategory")

    tmp = "__TMP__"
    obj1 = Category.objects.filter(id=1).first()
    if obj1 and obj1.name != "운동":
        obj1.name = f"{tmp}{obj1.name}"
        obj1.save(update_fields=["name"])

    obj2 = Category.objects.filter(id=2).first()
    if obj2 and obj2.name != "식습관":
        obj2.name = f"{tmp}{obj2.name}"
        obj2.save(update_fields=["name"])

    # 최종 이름 덮어쓰기
    if obj1:
        obj1.name = "운동"
        obj1.save(update_fields=["name"])
    if obj2:
        obj2.name = "식습관"
        obj2.save(update_fields=["name"])

    # 3, 4 생성
    existing = dict(Category.objects.values_list("id", "name"))
    for pk, name in TARGET:
        if pk not in existing and not Category.objects.filter(name=name).exists():
            Category.objects.create(id=pk, name=name)

def backwards(apps, schema_editor):
    Category = apps.get_model("challenges", "ChallengeCategory")
    # 롤백 시 기존 1,2 복원 및 3,4 삭제
    if Category.objects.filter(id=1).exists():
        Category.objects.filter(id=1).update(name="독서")
    if Category.objects.filter(id=2).exists():
        Category.objects.filter(id=2).update(name="운동")
    Category.objects.filter(id__in=[3,4]).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("challenges", "0006_completeimage_review_reasons_and_more"),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
