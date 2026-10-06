from rest_framework.renderers import JSONRenderer


class EnvelopeJSONRenderer(JSONRenderer):
    """
    Wraps successful responses as ``{"success": true, "data": ...}``.

    Error responses are already shaped by ``api_exception_handler``; paginated
    responses are shaped by ``StandardPagination`` and flagged with
    ``response.envelope = True`` so they are not wrapped twice.
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        if response is not None:
            if response.status_code == 204:
                return b""
            already_wrapped = getattr(response, "envelope", False) or response.status_code >= 400
            if not already_wrapped:
                data = {"success": True, "data": data}
        return super().render(data, accepted_media_type, renderer_context)
