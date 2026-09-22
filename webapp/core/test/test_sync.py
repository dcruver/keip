import json
import os
from pathlib import PurePosixPath
from typing import Mapping

import pytest

from core.sync import (
    sync,
    VolumeConfig,
    _spring_cloud_k8s_config,
    SECRETS_ROOT,
    _new_deployment,
    _create_pod_template,
    _spring_app_config_env_var,
    _get_java_jdk_options,
    _generate_container_env_vars,
    _get_server_ssl_config,
)
from webapp.routes.test.test_webapp import load_json_as_dict

JDK_OPTIONS_ENV_NAME = "JDK_JAVA_OPTIONS"


def test_empty_parent_raises_exception():
    with pytest.raises(KeyError):
        sync({})


def test_full_integration_route(full_route):
    response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    actual = sync(full_route)

    assert response == actual


def test_vol_config_missing_route_map_raise_exception(full_route):
    del full_route["parent"]["spec"]["routeConfigMap"]
    with pytest.raises(KeyError):
        VolumeConfig(full_route["parent"]["spec"])


def test_vol_config_missing_optional_vols_no_fail(full_route):
    del full_route["parent"]["spec"]["secretSources"]
    del full_route["parent"]["spec"]["persistentVolumeClaims"]
    del full_route["parent"]["spec"]["configMaps"]
    vol_conf = VolumeConfig(full_route["parent"]["spec"])

    assert len(vol_conf.get_volumes()) > 0
    assert len(vol_conf.get_mounts()) > 0


def test_spring_app_config_json_missing_props_sources(full_route):
    del full_route["parent"]["spec"]["propSources"]

    spring_conf = _spring_cloud_k8s_config(full_route["parent"])

    assert spring_conf["kubernetes"]["secrets"] == {"paths": SECRETS_ROOT}


def test_spring_app_config_json_missing_secret_sources(full_route):
    del full_route["parent"]["spec"]["secretSources"]

    spring_conf = _spring_cloud_k8s_config(full_route["parent"])

    assert spring_conf["kubernetes"]["config"]["sources"] is not None


def test_spring_app_config_json_missing_props_and_secret_sources_jks_keystore(
    full_route,
):
    del full_route["parent"]["spec"]["propSources"]
    del full_route["parent"]["spec"]["secretSources"]
    spring_conf = _spring_app_config_env_var(full_route["parent"])
    actual_json = spring_conf["value"]

    assert spring_conf["name"] == "SPRING_APPLICATION_JSON"

    expected_json = json.dumps(
        {
            "spring": {"application": {"name": "testroute"}},
            "server": {
                "ssl": {
                    "key-alias": "certificate",
                    "key-store": "/etc/keystore/test-keystore.jks",
                    "key-store-type": "JKS",
                },
                "port": 8443,
            },
            "management": {
                "endpoint": {
                    "health": {"enabled": True},
                    "prometheus": {"enabled": True},
                },
                "endpoints": {"web": {"exposure": {"include": "health,prometheus"}}},
            },
        }
    )

    assert actual_json == expected_json


def test_spring_app_config_json_missing_props_and_secret_sources_pkcs12_keystore(
    full_route,
):
    del full_route["parent"]["spec"]["propSources"]
    del full_route["parent"]["spec"]["secretSources"]
    del full_route["parent"]["spec"]["tls"]["keystore"]["jks"]
    full_route["parent"]["spec"]["tls"]["keystore"] = {
        "pkcs12": {
            "alias": "1",
            "secretName": "test-tls-secret",
            "key": "test-keystore.p12",
            "passwordSecretRef": "keystore-password-ref",
        }
    }

    spring_conf = _spring_app_config_env_var(full_route["parent"])
    actual_json = spring_conf["value"]

    assert spring_conf["name"] == "SPRING_APPLICATION_JSON"

    expected_json = json.dumps(
        {
            "spring": {"application": {"name": "testroute"}},
            "server": {
                "ssl": {
                    "key-alias": "1",
                    "key-store": "/etc/keystore/test-keystore.p12",
                    "key-store-type": "PKCS12",
                },
                "port": 8443,
            },
            "management": {
                "endpoint": {
                    "health": {"enabled": True},
                    "prometheus": {"enabled": True},
                },
                "endpoints": {"web": {"exposure": {"include": "health,prometheus"}}},
            },
        }
    )

    assert actual_json == expected_json


def test_pod_template_no_annotations(full_route):
    del full_route["parent"]["spec"]["annotations"]

    deployment = _new_deployment(full_route["parent"])

    pod_template = deployment["spec"]["template"]
    assert pod_template["metadata"].get("annotations") is None


def test_pod_template_empty_annotations(full_route):
    full_route["parent"]["spec"]["annotations"] = {}

    deployment = _new_deployment(full_route["parent"])

    pod_template = deployment["spec"]["template"]
    assert pod_template["metadata"].get("annotations") is None


def test_pod_template_no_tls(full_route):
    del full_route["parent"]["spec"]["tls"]

    deployment = _new_deployment(full_route["parent"])

    check_pod_probe_protocol(deployment, "HTTP", 8080)
    check_volume_absent(deployment, "truststore")
    check_volume_mounts_absent(deployment, "truststore")
    check_volume_absent(deployment, "keystore")
    check_volume_mounts_absent(deployment, "keystore")


def test_pod_template_no_truststore(full_route):
    del full_route["parent"]["spec"]["tls"]["truststore"]

    deployment = _new_deployment(full_route["parent"])

    check_pod_probe_protocol(deployment, "HTTPS", 8443)
    check_volume_absent(deployment, "truststore")
    check_volume_mounts_absent(deployment, "truststore")


def test_pod_template_no_keystore(full_route):
    del full_route["parent"]["spec"]["tls"]["keystore"]

    deployment = _new_deployment(full_route["parent"])

    check_pod_probe_protocol(deployment, "HTTP", 8080)
    check_volume_absent(deployment, "keystore")
    check_volume_mounts_absent(deployment, "keystore")


def test_jdk_options_pkcs12_truststore_type(full_route):
    tls_config = full_route["parent"]["spec"]["tls"]
    options = _get_java_jdk_options(tls_config)

    assert options["name"] == JDK_OPTIONS_ENV_NAME

    expected_options = (
        "-Djavax.net.ssl.trustStore="
        + str(PurePosixPath("/", "etc", "cabundle", "test-truststore.p12"))
        + " -Djavax.net.ssl.trustStorePassword= -Djavax.net.ssl.trustStoreType=PKCS12"
    )
    assert options["value"] == expected_options


def test_jdk_options_jks_truststore_type(full_route):
    tls_config = full_route["parent"]["spec"]["tls"]
    tls_config["truststore"] = {
        "jks": {"configMapName": "test-tls-cm", "key": "test-truststore.jks"}
    }

    options = _get_java_jdk_options(tls_config)
    assert options["name"] == JDK_OPTIONS_ENV_NAME

    expected_options = (
        "-Djavax.net.ssl.trustStore="
        + str(PurePosixPath("/", "etc", "cabundle", "test-truststore.jks"))
        + " -Djavax.net.ssl.trustStorePassword=changeit -Djavax.net.ssl.trustStoreType=JKS"
    )
    assert options["value"] == expected_options


def test_env_vars_no_keystore(full_route):
    del full_route["parent"]["spec"]["tls"]["keystore"]

    options = _generate_container_env_vars(full_route["parent"])

    assert not any(x for x in options if x.get("name") == "SERVER_SSL_KEYSTOREPASSWORD")


def test_volume_pkcs12_keystore_and_pkcs12_truststore(full_route):
    del full_route["parent"]["spec"]["tls"]["keystore"]
    full_route["parent"]["spec"]["tls"]["keystore"] = {
        "pkcs12": {
            "secretName": "test-tls-secret",
            "key": "test-keystore.p12",
            "passwordSecretRef": "keystore-password-ref",
        }
    }
    expected_keystore_volume = {
        "name": "keystore",
        "secret": {
            "secretName": "test-tls-secret",
            "items": [{"key": "test-keystore.p12", "path": "test-keystore.p12"}],
        },
    }

    expected_truststore_volume = {
        "name": "truststore",
        "configMap": {
            "name": "test-tls-cm",
            "items": [{"key": "test-truststore.p12", "path": "test-truststore.p12"}],
        },
    }

    response = sync(full_route)
    volumes = response["children"][0]["spec"]["template"]["spec"]["volumes"]
    actual_keystore_volume = None
    actual_truststore_volume = None
    for volume in volumes:
        if volume["name"] == "keystore":
            actual_keystore_volume = volume
        elif volume["name"] == "truststore":
            actual_truststore_volume = volume

    assert actual_keystore_volume == expected_keystore_volume
    assert actual_truststore_volume == expected_truststore_volume


def test_volume_jks_keystore_and_jks_truststore(full_route):
    del full_route["parent"]["spec"]["tls"]["truststore"]
    full_route["parent"]["spec"]["tls"]["truststore"] = {
        "jks": {"configMapName": "test-tls-cm", "key": "test-truststore.jks"}
    }
    expected_keystore_volume = {
        "name": "keystore",
        "secret": {
            "secretName": "test-tls-secret",
            "items": [{"key": "test-keystore.jks", "path": "test-keystore.jks"}],
        },
    }

    expected_truststore_volume = {
        "name": "truststore",
        "configMap": {
            "name": "test-tls-cm",
            "items": [{"key": "test-truststore.jks", "path": "test-truststore.jks"}],
        },
    }
    response = sync(full_route)
    volumes = response["children"][0]["spec"]["template"]["spec"]["volumes"]
    actual_keystore_volume = None
    actual_truststore_volume = None
    for volume in volumes:
        if volume["name"] == "keystore":
            actual_keystore_volume = volume
        elif volume["name"] == "truststore":
            actual_truststore_volume = volume

    assert actual_keystore_volume == expected_keystore_volume
    assert actual_truststore_volume == expected_truststore_volume


def test_jks_keystore_custom_key_alias(full_route):
    full_route["parent"]["spec"]["tls"]["keystore"]["jks"]["alias"] = "mykeyalias"
    expected_ssl_config = {
        "ssl": {
            "key-alias": "mykeyalias",
            "key-store": "/etc/keystore/test-keystore.jks",
            "key-store-type": "JKS",
        },
        "port": 8443,
    }

    actual_ssl_config = _get_server_ssl_config(full_route["parent"])

    assert actual_ssl_config == expected_ssl_config


def test_jks_keystore_no_key_alias(full_route):
    expected_ssl_config = {
        "ssl": {
            "key-alias": "certificate",
            "key-store": "/etc/keystore/test-keystore.jks",
            "key-store-type": "JKS",
        },
        "port": 8443,
    }

    actual_ssl_config = _get_server_ssl_config(full_route["parent"])

    assert actual_ssl_config == expected_ssl_config


def test_pkcs12_keystore(full_route):
    del full_route["parent"]["spec"]["tls"]["keystore"]["jks"]
    full_route["parent"]["spec"]["tls"]["keystore"] = {
        "pkcs12": {
            "secretName": "test-tls-secret",
            "key": "test-keystore.p12",
            "passwordSecretRef": "keystore-password-ref",
        }
    }
    expected_ssl_config = {
        "ssl": {
            "key-alias": "1",
            "key-store": "/etc/keystore/test-keystore.p12",
            "key-store-type": "PKCS12",
        },
        "port": 8443,
    }

    actual_ssl_config = _get_server_ssl_config(full_route["parent"])

    assert actual_ssl_config == expected_ssl_config


def test_env_var_service_name(full_route):
    actual_env_vars = _generate_container_env_vars(full_route["parent"])
    actual_service_name_env_var = next(
        (
            actual_env_var
            for actual_env_var in actual_env_vars
            if actual_env_var["name"] == "SERVICE_NAME"
        ),
        None,
    )
    expected_service_name_env_var = {"name": "SERVICE_NAME", "value": "testroute"}
    assert expected_service_name_env_var == actual_service_name_env_var


def test_no_additional_env_vars(full_route):
    additional_env_vars_to_remove_from_expected_response = [
        "ADDITIONAL_ENV_VAR_1",
        "ADDITIONAL_ENV_VAR_2",
    ]

    expected_response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    env_vars_in_response = list(
        expected_response["children"][0]["spec"]["template"]["spec"]["containers"][0][
            "env"
        ]
    )
    for env_var in env_vars_in_response:
        if (
            env_var["name"] == additional_env_vars_to_remove_from_expected_response[0]
            or env_var["name"]
            == additional_env_vars_to_remove_from_expected_response[1]
        ):
            expected_response["children"][0]["spec"]["template"]["spec"]["containers"][
                0
            ]["env"].remove(env_var)

    del full_route["parent"]["spec"]["env"]
    actual_response = sync(full_route)

    assert expected_response == actual_response


def test_no_env_from(full_route):
    expected_response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    del expected_response["children"][0]["spec"]["template"]["spec"]["containers"][0][
        "envFrom"
    ]

    del full_route["parent"]["spec"]["envFrom"]
    actual_response = sync(full_route)

    assert expected_response == actual_response


def test_env_from_config_map_ref_optional_property_not_present(full_route):
    expected_response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    expected_response["children"][0]["spec"]["template"]["spec"]["containers"][0][
        "envFrom"
    ][0]["configMapRef"].pop("optional", None)

    full_route["parent"]["spec"]["envFrom"][0]["configMapRef"].pop("optional", None)
    actual_response = sync(full_route)

    assert expected_response == actual_response


def test_env_from_config_map_ref_optional_false(full_route):
    expected_response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    expected_response["children"][0]["spec"]["template"]["spec"]["containers"][0][
        "envFrom"
    ][0]["configMapRef"]["optional"] = False

    full_route["parent"]["spec"]["envFrom"][0]["configMapRef"]["optional"] = False
    actual_response = sync(full_route)

    assert expected_response == actual_response


def test_env_from_config_map_ref_optional_true(full_route):
    expected_response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    expected_response["children"][0]["spec"]["template"]["spec"]["containers"][0][
        "envFrom"
    ][0]["configMapRef"]["optional"] = True

    full_route["parent"]["spec"]["envFrom"][0]["configMapRef"]["optional"] = True
    actual_response = sync(full_route)

    assert expected_response == actual_response


def test_env_from_secret_ref_optional_property_not_present(full_route):
    expected_response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    expected_response["children"][0]["spec"]["template"]["spec"]["containers"][0][
        "envFrom"
    ][1]["secretRef"].pop("optional", None)

    full_route["parent"]["spec"]["envFrom"][1]["secretRef"].pop("optional", None)
    actual_response = sync(full_route)

    assert expected_response == actual_response


def test_env_from_secret_ref_optional_false(full_route):
    expected_response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    expected_response["children"][0]["spec"]["template"]["spec"]["containers"][0][
        "envFrom"
    ][1]["secretRef"]["optional"] = False

    full_route["parent"]["spec"]["envFrom"][1]["secretRef"]["optional"] = False
    actual_response = sync(full_route)

    assert expected_response == actual_response


def test_env_from_secret_ref_optional_true(full_route):
    expected_response = load_json_as_dict(
        f"{os.path.dirname(os.path.abspath(__file__))}/json/full-response.json"
    )
    expected_response["children"][0]["spec"]["template"]["spec"]["containers"][0][
        "envFrom"
    ][1]["secretRef"]["optional"] = True

    full_route["parent"]["spec"]["envFrom"][1]["secretRef"]["optional"] = True
    actual_response = sync(full_route)

    assert expected_response == actual_response


def test_deployment_missing_labels(full_route):
    del full_route["parent"]["spec"]["labels"]

    deployment = _new_deployment(full_route["parent"])

    labels = deployment["metadata"]["labels"]
    assert len(labels) > 0


def test_deployment_empty_labels(full_route):
    full_route["parent"]["spec"]["labels"] = {}

    deployment = _new_deployment(full_route["parent"])

    labels = deployment["metadata"]["labels"]
    assert len(labels) > 0


def test_deployment_missing_annotations(full_route):
    del full_route["parent"]["spec"]["annotations"]

    deployment = _new_deployment(full_route["parent"])

    assert "annotations" in deployment["metadata"]
    annotations = deployment["metadata"]["annotations"]
    assert len(annotations) == 0


def test_deployment_empty_annotations(full_route):
    full_route["parent"]["spec"]["annotations"] = {}

    deployment = _new_deployment(full_route["parent"])

    assert "annotations" in deployment["metadata"]
    annotations = deployment["metadata"]["annotations"]
    assert len(annotations) == 0


def test_pod_missing_resources(full_route):
    del full_route["parent"]["spec"]["resources"]

    pod = _create_pod_template(
        full_route["parent"], labels=None, integration_image=None
    )

    assert "resources" not in pod["spec"]["containers"][0]


def test_pod_resources_limits_only(full_route):
    del full_route["parent"]["spec"]["resources"]["requests"]

    pod = _create_pod_template(
        full_route["parent"], labels=None, integration_image=None
    )

    pod_resources = pod["spec"]["containers"][0]["resources"]
    assert "requests" not in pod_resources
    assert pod_resources["limits"].get("memory") == "5Gi"


def test_pod_resources_requests_only(full_route):
    del full_route["parent"]["spec"]["resources"]["limits"]

    pod = _create_pod_template(
        full_route["parent"], labels=None, integration_image=None
    )

    pod_resources = pod["spec"]["containers"][0]["resources"]
    assert "limits" not in pod_resources
    assert pod_resources["requests"].get("cpu") == "1"
    assert pod_resources["requests"].get("memory") == "2Gi"


def check_volume_absent(deployment: Mapping, name: str):
    vols = deployment["spec"]["template"]["spec"]["volumes"]
    vol_names = [v["name"] for v in vols]
    assert name not in vol_names


def check_pod_probe_protocol(deployment: Mapping, scheme: str, port: int):
    liveness_probe = get_container(deployment)["livenessProbe"]
    readiness_probe = get_container(deployment)["readinessProbe"]

    assert liveness_probe["httpGet"]["port"] == port
    assert liveness_probe["httpGet"]["scheme"] == scheme

    assert readiness_probe["httpGet"]["port"] == port
    assert readiness_probe["httpGet"]["scheme"] == scheme


def check_volume_mounts_absent(deployment: Mapping, name: str):
    mounts = get_container(deployment)["volumeMounts"]
    mnt_names = [m["name"] for m in mounts]
    assert name not in mnt_names


def get_container(deployment: Mapping) -> Mapping:
    pod_template = deployment["spec"]["template"]
    return pod_template["spec"]["containers"][0]


def test_per_route_image_override(full_route):
    """When spec.image is set, the deployment should use that image instead of the default."""
    custom_image = "registry.example.com/my-app:1.0"
    full_route["parent"]["spec"]["image"] = custom_image

    result = sync(full_route)

    deployment = result["children"][0]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == custom_image


def test_per_route_image_default_when_absent(full_route):
    """When spec.image is not set, the deployment should use the global default."""
    # Ensure no image field
    full_route["parent"]["spec"].pop("image", None)

    result = sync(full_route)

    deployment = result["children"][0]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    # Should use the default from config (INTEGRATION_CONTAINER_IMAGE)
    import config as cfg
    assert container["image"] == cfg.INTEGRATION_CONTAINER_IMAGE


def test_init_containers_passed_through(full_route):
    """spec.initContainers reaches the pod template unmodified."""
    init = [
        {
            "name": "bootstrap",
            "image": "curlimages/curl:8.11.0",
            "command": ["sh", "-c", "curl -sf http://example.svc:6333/ready"],
        }
    ]
    full_route["parent"]["spec"]["initContainers"] = init

    result = sync(full_route)

    pod_spec = result["children"][0]["spec"]["template"]["spec"]
    assert pod_spec["initContainers"] == init


def test_init_containers_preserve_arbitrary_fields(full_route):
    """Fields the CRD does not enumerate survive; the schema sets
    x-kubernetes-preserve-unknown-fields so the API server does not prune them."""
    init = [
        {
            "name": "bootstrap",
            "image": "busybox:1.36",
            "args": ["true"],
            "securityContext": {"readOnlyRootFilesystem": True},
            "resources": {"limits": {"cpu": "100m"}},
        }
    ]
    full_route["parent"]["spec"]["initContainers"] = init

    result = sync(full_route)

    pod_spec = result["children"][0]["spec"]["template"]["spec"]
    assert pod_spec["initContainers"][0]["securityContext"] == {
        "readOnlyRootFilesystem": True
    }
    assert pod_spec["initContainers"][0]["resources"] == {"limits": {"cpu": "100m"}}


def test_init_containers_key_omitted_when_absent(full_route):
    """With no spec.initContainers the key is absent from the pod spec."""
    full_route["parent"]["spec"].pop("initContainers", None)

    result = sync(full_route)

    pod_spec = result["children"][0]["spec"]["template"]["spec"]
    assert "initContainers" not in pod_spec
