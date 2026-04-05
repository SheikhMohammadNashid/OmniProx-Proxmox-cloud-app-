"""Tests for guest-agent IP discovery (POST vs GET, response shapes)."""
import unittest
from unittest.mock import MagicMock, patch

from backend.services.proxmox_client import ProxmoxClient


class ProxmoxIpTests(unittest.TestCase):
    def test_get_normalizes_null_data(self):
        raw = ProxmoxClient._normalize_agent_interface_list(None)
        self.assertEqual(raw, [])

    def test_normalize_list_of_ifaces(self):
        ifaces = [
            {"name": "lo", "ip-addresses": []},
            {
                "name": "ens18",
                "ip-addresses": [
                    {"ip-address-type": "ipv4", "ip-address": "192.168.1.50", "prefix": 24}
                ],
            },
        ]
        self.assertEqual(ProxmoxClient._normalize_agent_interface_list(ifaces), ifaces)
        self.assertEqual(ProxmoxClient._first_usable_ipv4(ifaces), "192.168.1.50")

    def test_normalize_proxmox_result_envelope(self):
        raw = {
            "result": [
                {
                    "name": "eth0",
                    "ip-addresses": [
                        {"ip-address-type": "IPv4", "ip-address": "10.0.0.7"},
                    ],
                }
            ]
        }
        norm = ProxmoxClient._normalize_agent_interface_list(raw)
        self.assertEqual(ProxmoxClient._first_usable_ipv4(norm), "10.0.0.7")

    def test_normalize_agent_error_object(self):
        raw = {"result": {"error": {"desc": "not running"}}}
        self.assertEqual(ProxmoxClient._normalize_agent_interface_list(raw), [])

    def test_agent_network_uses_post_then_parses(self):
        client = ProxmoxClient(
            base_url="https://pve.example:8006/api2/json",
            node="n1",
            token_id="user@pam!x",
            token_secret="secret",
            verify_ssl=False,
            dry_run=False,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "result": [
                    {
                        "name": "ens3",
                        "ip-addresses": [
                            {"ip-address-type": "ipv4", "ip-address": "172.16.0.22"},
                        ],
                    }
                ]
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.services.proxmox_client.requests.post", return_value=mock_resp) as p:
            raw = client._agent_network_get_interfaces_raw("n1", 105)
            p.assert_called_once()
        ip = ProxmoxClient._first_usable_ipv4(ProxmoxClient._normalize_agent_interface_list(raw))
        self.assertEqual(ip, "172.16.0.22")

    def test_agent_network_falls_back_to_get_on_405(self):
        client = ProxmoxClient(
            base_url="https://pve.example:8006/api2/json",
            node="n1",
            token_id="user@pam!x",
            token_secret="secret",
            verify_ssl=False,
            dry_run=False,
        )

        bad = MagicMock()
        bad.status_code = 405
        bad.raise_for_status = MagicMock()

        good = MagicMock()
        good.status_code = 200
        good.json.return_value = {
            "data": {
                "result": [
                    {
                        "name": "eth0",
                        "ip-addresses": [
                            {"ip-address-type": "ipv4", "ip-address": "192.168.5.3"},
                        ],
                    }
                ]
            }
        }
        good.raise_for_status = MagicMock()

        with (
            patch("backend.services.proxmox_client.requests.post", return_value=bad),
            patch("backend.services.proxmox_client.requests.get", return_value=good) as g,
        ):
            raw = client._agent_network_get_interfaces_raw("n1", 200)
            g.assert_called_once()
        ip = ProxmoxClient._first_usable_ipv4(ProxmoxClient._normalize_agent_interface_list(raw))
        self.assertEqual(ip, "192.168.5.3")


if __name__ == "__main__":
    unittest.main()
