from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[2]
EBS = ROOT / "infra" / "kubernetes" / "observability" / "ebs"
STORAGE_CLASS = "workforce-ebs-gp3-retain"


def _yaml(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((EBS / name).read_text()))


def test_storage_class_uses_encrypted_retained_gp3() -> None:
    storage_class = _yaml("storage-class.yaml")

    assert storage_class["kind"] == "StorageClass"
    assert storage_class["metadata"]["name"] == STORAGE_CLASS
    assert storage_class["provisioner"] == "ebs.csi.aws.com"
    assert storage_class["parameters"] == {"type": "gp3", "encrypted": "true"}
    assert storage_class["reclaimPolicy"] == "Retain"
    assert storage_class["volumeBindingMode"] == "WaitForFirstConsumer"
    assert storage_class["allowVolumeExpansion"] is True


def test_ebs_csi_driver_is_pinned_and_uses_projected_web_identity() -> None:
    versions = dict(
        line.split("=", 1)
        for line in (EBS / "versions.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    values = _yaml("aws-ebs-csi-driver-values.yaml")
    controller = values["controller"]

    assert versions["AWS_EBS_CSI_DRIVER_CHART_VERSION"] == "2.63.1"
    assert controller["serviceAccount"]["name"] == "ebs-csi-controller-sa"
    assert controller["serviceAccount"]["create"] is True
    env = {item["name"]: item["value"] for item in controller["env"]}
    assert env == {
        "AWS_ROLE_ARN": "WORKFORCE_EBS_CSI_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE": "/var/run/secrets/aws/token",
    }
    token = controller["volumes"][0]["projected"]["sources"][0]["serviceAccountToken"]
    assert token["audience"] == "sts.amazonaws.com"
    assert token["path"] == "token"
    assert controller["volumeMounts"][0]["mountPath"] == "/var/run/secrets/aws"


def test_prometheus_and_grafana_request_independent_ebs_storage() -> None:
    values = _yaml("kube-prometheus-stack-values.yaml")
    prometheus = values["prometheus"]["prometheusSpec"]
    prometheus_claim = prometheus["storageSpec"]["volumeClaimTemplate"]["spec"]
    grafana = values["grafana"]["persistence"]

    assert prometheus["retention"] == "7d"
    assert prometheus_claim["storageClassName"] == STORAGE_CLASS
    assert prometheus_claim["resources"]["requests"]["storage"] == "10Gi"
    assert prometheus_claim["accessModes"] == ["ReadWriteOnce"]
    assert grafana["enabled"] is True
    assert grafana["storageClassName"] == STORAGE_CLASS
    assert grafana["size"] == "2Gi"
    assert grafana["accessModes"] == ["ReadWriteOnce"]


def test_grafana_is_publicly_exposed_as_anonymous_viewer_under_subpath() -> None:
    values = _yaml("kube-prometheus-stack-values.yaml")
    grafana = values["grafana"]
    ingress = _yaml("grafana-public-ingress.yaml")

    assert grafana["grafana.ini"]["server"] == {
        "root_url": "%(protocol)s://%(domain)s/grafana/",
        "serve_from_sub_path": True,
    }
    assert grafana["grafana.ini"]["auth.anonymous"] == {
        "enabled": True,
        "org_role": "Viewer",
    }
    assert grafana["grafana.ini"]["auth"]["disable_login_form"] is True
    assert ingress["metadata"]["namespace"] == "monitoring"
    assert ingress["spec"]["ingressClassName"] == "nginx"
    path = ingress["spec"]["rules"][0]["http"]["paths"][0]
    assert path["path"] == "/grafana"
    assert path["pathType"] == "Prefix"
    assert path["backend"]["service"] == {
        "name": "workforce-monitoring-grafana",
        "port": {"number": 80},
    }


def test_loki_requests_its_own_ebs_storage() -> None:
    values = _yaml("loki-values.yaml")
    persistence = values["singleBinary"]["persistence"]

    assert values["deploymentMode"] == "SingleBinary"
    assert values["singleBinary"]["replicas"] == 1
    assert persistence["enabled"] is True
    assert persistence["storageClass"] == STORAGE_CLASS
    assert persistence["size"] == "10Gi"
    assert persistence["accessModes"] == ["ReadWriteOnce"]


def test_local_compose_remains_on_named_volumes_not_ebs() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())

    assert "workforce-prometheus-data" in compose["volumes"]
    assert "workforce-grafana-data" in compose["volumes"]
    assert "workforce-loki-data" in compose["volumes"]
    assert "ebs.csi.aws.com" not in (ROOT / "compose.yaml").read_text()
