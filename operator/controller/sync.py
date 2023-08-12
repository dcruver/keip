#!/usr/bin/env python

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import List, Mapping, Optional

# TODO: Abstract configuration property resolution in a separate module
INTEGRATION_IMAGE = os.getenv("INTEGRATION_IMAGE", "keip-integration")

SECRETS_ROOT = "/etc/secrets"


class VolumeConfig:
    """
    Handles creating a pod's volumes and volumeMounts based on the following IntegrationRoute inputs:
        - routeConfigMap
        - secretSources
        - persistentVolumeClaims
    """

    _route_vol_name = "integration-route-config"

    def __init__(self, parent_spec) -> None:
        self._route_config = parent_spec["routeConfigMap"]
        self._secret_srcs = parent_spec.get("secretSources", [])
        self._pvcs = parent_spec.get("persistentVolumeClaims", [])

    def get_volumes(self) -> List[Mapping]:
        volumes = [
            {
                "name": self._route_vol_name,
                "configMap": {
                    "name": self._route_config,
                },
            }
        ]

        for secret in self._secret_srcs:
            volumes.append({"name": secret, "secret": {"secretName": secret}})

        for pvc_spec in self._pvcs:
            volumes.append(
                {
                    "name": pvc_spec["claimName"],
                    "persistentVolumeClaim": {"claimName": pvc_spec["claimName"]},
                }
            )

        return volumes

    def get_mounts(self) -> List[Mapping]:
        volumeMounts = [
            {
                "name": self._route_vol_name,
                "mountPath": "/var/spring/xml",
            }
        ]

        for secret in self._secret_srcs:
            volumeMounts.append(
                {
                    "name": secret,
                    "readOnly": True,
                    "mountPath": str(Path(SECRETS_ROOT, secret)),
                }
            )

        for pvc_spec in self._pvcs:
            volumeMounts.append(
                {
                    "name": pvc_spec["claimName"],
                    "mountPath": pvc_spec["mountPath"],
                }
            )

        return volumeMounts


def spring_cloud_k8s_config(parent) -> Optional[Mapping]:
    """Generates the spring-cloud-kubernetes config that's passed as an env var to the Spring app"""
    metadata = parent["metadata"]

    props_srcs = parent["spec"].get("propSources")
    secret_srcs = parent["spec"].get("secretSources")

    if not props_srcs and not secret_srcs:
        return None

    return {
        "spring": {
            "config.import": "kubernetes:",
            "application": {"name": metadata["name"]},
            "cloud": {
                "kubernetes": {
                    "config": {
                        "fail-fast": True,
                        "namespace": metadata["namespace"],
                        "sources": props_srcs,
                    },
                    "secrets": {"paths": SECRETS_ROOT},
                }
            },
        }
    }


def create_pod_template(parent, labels, integration_image):
    """TODO: Should add some resource constraints for containers. Add constraint values to CRD."""

    vol_config = VolumeConfig(parent["spec"])

    pod_template = {
        "metadata": {"labels": labels},
        "spec": {
            "serviceAccountName": "spring-cloud-kubernetes",
            "containers": [
                {
                    "name": "integration-app",
                    "image": integration_image,
                    "volumeMounts": vol_config.get_mounts(),
                }
            ],
            "volumes": vol_config.get_volumes(),
        },
    }

    spring_app_config = spring_cloud_k8s_config(parent)
    if spring_app_config:
        pod_template["spec"]["containers"][0]["env"] = [
            {
                "name": "SPRING_APPLICATION_JSON",
                "value": json.dumps(spring_app_config),
            }
        ]

    return pod_template


def new_deployment(parent):
    parent_metadata = parent["metadata"]

    labels = {
        "app.kubernetes.io/managed-by": "integrationroute-controller",
        "app.kubernetes.io/name": "integrationroute",
        "app.kubernetes.io/instance": f'integrationroute-{parent_metadata["name"]}',
        "app.kubernetes.io/version": "latest",
    }

    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": parent_metadata["name"],
            "labels": labels,
        },
        "spec": {
            "selector": {
                "matchLabels": {
                    "app.kubernetes.io/instance": labels["app.kubernetes.io/instance"]
                }
            },
            "replicas": parent["spec"]["replicas"],
            "template": create_pod_template(parent, labels, INTEGRATION_IMAGE),
        },
    }

    return deployment


# TODO: Consider using a production-ready server rather than the built-in http.server
# TODO: Add some typing to request and response objects
# TODO: Add some unit testing
class ServiceRouteController(BaseHTTPRequestHandler):
    def sync(self, parent):
        desired = {"status": {}, "children": []}
        desired["children"].append(new_deployment(parent))
        return desired

    def do_POST(self):
        try:
            observed = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length")))
            )
            desired = self.sync(observed["parent"])
        except Exception as e:
            self.send_error(500, message=str(e))
        else:
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(desired).encode())


HTTPServer(("", 7080), ServiceRouteController).serve_forever()
