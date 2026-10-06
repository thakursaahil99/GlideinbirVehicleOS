from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Channel, Notification
from .services import NotificationService


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ("id", "event", "title", "body", "data", "is_read", "read_at", "created_at")
        read_only_fields = fields

    def get_is_read(self, obj) -> bool:
        return obj.read_at is not None


class MarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), required=False)


@extend_schema_view(list=extend_schema(tags=["notifications"], summary="My in-app notifications"))
class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()
    filter_backends = []

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user, channel=Channel.IN_APP)
        if self.request.query_params.get("unread") in ("1", "true"):
            qs = qs.filter(read_at__isnull=True)
        return qs.order_by("-created_at")

    @extend_schema(tags=["notifications"], responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = Notification.objects.filter(recipient=request.user, channel=Channel.IN_APP,
                                            read_at__isnull=True).count()
        return Response({"unread": count})

    @extend_schema(tags=["notifications"], summary="Mark some (ids) or all notifications read",
                   request=MarkReadSerializer, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = NotificationService.mark_read(request.user, serializer.validated_data.get("ids"))
        return Response({"updated": updated})
