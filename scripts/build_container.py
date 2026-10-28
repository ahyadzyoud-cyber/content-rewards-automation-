"""Build through the existing proxy and CA trust without saving credential values."""
import argparse
import os
import socket
import ssl
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="content-rewards-dev:onboarding")
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args = ["docker", "build"]
    proxy_names = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")
    proxy_hosts = {urlsplit(os.environ[name]).hostname for name in proxy_names
                   if name.lower() != "no_proxy" and os.environ.get(name)}
    if proxy_hosts:
        # Docker's build DNS may not know platform-provided proxy aliases. Reuse
        # their existing resolution and route; never connect around the proxy.
        args += ["--network=host"]
        for host in sorted(proxy_hosts):
            address = socket.getaddrinfo(host, None, family=socket.AF_INET)[0][4][0]
            args += ["--add-host", host + ":" + address]
    for name in proxy_names:
        if name in os.environ:
            args += ["--build-arg", name]
    ca_bundle = os.environ.get("SSL_CERT_FILE") or ssl.get_default_verify_paths().cafile
    if ca_bundle and Path(ca_bundle).is_file():
        # Public CA certificates are mounted only at build time, never copied
        # into the image. Dockerfile retains TLS and apt signature verification.
        args += ["--secret", "id=platform-ca,src=" + ca_bundle]
    args += ["-t", options.tag, "."]
    config = root / ".data/docker-config"
    config.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.setdefault("DOCKER_CONFIG", str(config))
    return subprocess.run(args, cwd=root, env=environment).returncode


if __name__ == "__main__":
    raise SystemExit(main())
