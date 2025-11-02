from rest_framework import serializers
from .models import CompleteImage, Comment

class CommentSerializer(serializers.ModelSerializer):
     user_name = serializers.CharField(source="user.name", read_only=True)
     user_id = serializers.IntegerField(source="user.id", read_only=True)

     class Meta:
          model = Comment
          fields = [
               "id",
               "user_id",
               "user_name",
               "content",
               "x_ratio",
               "y_ratio",
               "created_at",
          ]
          read_only_fields = ["id", "user_id", "user_name", "created_at"]


class CommentCreateSerializer(serializers.ModelSerializer):
     class Meta:
          model = Comment
          fields = ["content", "x_ratio", "y_ratio"]

     def create(self, validated_data):
          """
          view에서 photo(CompleteImage)와 user를 넘겨줘야 함
          """
          photo = self.context["photo"]
          user = self.context["user"]
          return Comment.objects.create(
               complete_image=photo,
               user=user,
               **validated_data,
          )


class CompleteImageDetailSerializer(serializers.ModelSerializer):
     user_name = serializers.CharField(source="user.name", read_only=True)
     user_id = serializers.IntegerField(source="user.id", read_only=True)
     comments = CommentSerializer(many=True, read_only=True)

     class Meta:
          model = CompleteImage
          fields = [
               "id",
               "user_id",
               "user_name",
               "image",
               "status",
               "date",
               "comment_count",
               "created_at",
               "comments",
          ]
          read_only_fields = fields


class CompleteImageListSerializer(serializers.ModelSerializer):
     user_name = serializers.CharField(source="user.name", read_only=True)
     user_id = serializers.IntegerField(source="user.id", read_only=True)

     class Meta:
          model = CompleteImage
          fields = [
               "id",
               "user_id",
               "user_name",
               "image",
               "comment_count",
               "status",
               "created_at",
          ]
          read_only_fields = fields
