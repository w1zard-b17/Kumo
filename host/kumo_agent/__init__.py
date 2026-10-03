"""kumo-agent: storage agent for the OpenBSD host.

The only process that touches the HDD bay. VMs authenticate with a per-VM
bearer token and address their media by opaque file id, never by path.
"""

__version__ = "1.0.0"
