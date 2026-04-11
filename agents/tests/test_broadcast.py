"""
Tests for agents.broadcast — the channel-layer shim.

Verifies that:
- When channels isn't installed, broadcast_project_update is a safe no-op.
- When a channel layer IS available (mocked), messages are dispatched to the
  correct group with the expected envelope.
"""
import unittest
from unittest.mock import MagicMock, patch

from agents import broadcast
from agents.broadcast import broadcast_project_update


class BroadcastNoChannelsTests(unittest.TestCase):
    def test_channels_unavailable_in_this_env(self):
        """Sanity: the dev box has no channels installed."""
        self.assertFalse(broadcast._CHANNELS_AVAILABLE)

    def test_broadcast_is_noop_when_channels_unavailable(self):
        """Calling broadcast with no channels should not raise."""
        broadcast_project_update(1, "agent_task_update", {"foo": "bar"})


class BroadcastWithMockedChannelsTests(unittest.TestCase):
    def test_broadcast_dispatches_to_correct_group(self):
        mock_layer = MagicMock()
        mock_layer.group_send = MagicMock()

        def fake_async_to_sync(fn):
            """Return a sync callable that just calls the mock directly."""
            def _call(*args, **kwargs):
                return fn(*args, **kwargs)
            return _call

        with patch.object(broadcast, "_CHANNELS_AVAILABLE", True), \
             patch.object(broadcast, "get_channel_layer", return_value=mock_layer), \
             patch.object(broadcast, "async_to_sync", side_effect=fake_async_to_sync):
            broadcast_project_update(42, "agent_task_update", {"status": "done"})

        mock_layer.group_send.assert_called_once()
        args, _ = mock_layer.group_send.call_args
        self.assertEqual(args[0], "project_42")
        message = args[1]
        self.assertEqual(message["type"], "project.update")
        self.assertEqual(message["event_type"], "agent_task_update")
        self.assertEqual(message["data"], {"status": "done"})

    def test_broadcast_noop_when_get_channel_layer_returns_none(self):
        with patch.object(broadcast, "_CHANNELS_AVAILABLE", True), \
             patch.object(broadcast, "get_channel_layer", return_value=None):
            # Must not raise.
            broadcast_project_update(1, "x", {})

    def test_broadcast_swallows_exceptions_from_layer(self):
        mock_layer = MagicMock()

        def fake_async_to_sync(fn):
            def _call(*args, **kwargs):
                raise RuntimeError("redis down")
            return _call

        with patch.object(broadcast, "_CHANNELS_AVAILABLE", True), \
             patch.object(broadcast, "get_channel_layer", return_value=mock_layer), \
             patch.object(broadcast, "async_to_sync", side_effect=fake_async_to_sync):
            # Must not raise even though the layer blew up.
            broadcast_project_update(1, "x", {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
