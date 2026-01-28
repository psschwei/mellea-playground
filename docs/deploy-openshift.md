# Deploying Mellea to OpenShift

This guide covers deploying Mellea Playground to a hosted OpenShift cluster.

## Prerequisites

### Required Tools

- **oc CLI**: OpenShift command-line tool ([install guide](https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html))
- **kubectl**: Kubernetes CLI (usually installed alongside oc)
- **kustomize**: Either standalone or via `kubectl apply -k` (kubectl 1.14+)

### Required Access

- Access to an OpenShift cluster with permissions to:
  - Create/manage resources in a namespace
  - Create PersistentVolumeClaims (cluster must support dynamic provisioning)
  - Create Routes for external access
- Access to a container registry (Quay.io, GHCR, or similar) where Mellea images are published

### Verify Prerequisites

```bash
# Check oc is installed and you're logged in
oc version
oc whoami

# Verify you have access to your target namespace
oc project mellea-system
# Or create it if you have permissions:
oc new-project mellea-system
```

## Deployment Steps

### Step 1: Create the Namespace

The kustomization creates the `mellea-system` namespace, but if your cluster requires pre-created namespaces:

```bash
oc create namespace mellea-system
# Or use the namespaces manifest directly:
oc apply -f k8s/base/namespaces/namespaces.yaml
```

### Step 2: Create Registry Credentials Secret

If pulling images from a private registry (e.g., Quay.io), create the image pull secret:

```bash
# Option 1: Using oc/kubectl create secret (recommended)
oc create secret docker-registry registry-credentials \
  --namespace=mellea-system \
  --docker-server=quay.io \
  --docker-username=YOUR_USERNAME \
  --docker-password=YOUR_PASSWORD_OR_TOKEN \
  --docker-email=YOUR_EMAIL

# Option 2: Using an existing Docker config
oc create secret generic registry-credentials \
  --namespace=mellea-system \
  --from-file=.dockerconfigjson=$HOME/.docker/config.json \
  --type=kubernetes.io/dockerconfigjson
```

### Step 3: Deploy with Kustomize

```bash
# From the repository root:
oc apply -k k8s/overlays/openshift/

# Or using the Makefile:
make deploy-openshift
```

This deploys:
- Backend API deployment and service
- Frontend deployment and service
- Redis deployment and service
- PersistentVolumeClaims for assets, workspaces, artifacts, and Redis data
- Routes for external HTTPS access
- RBAC resources (service accounts, roles, bindings)

### Step 4: Verify Deployment

```bash
# Check all pods are running
oc get pods -n mellea-system

# Expected output:
# NAME                               READY   STATUS    RESTARTS   AGE
# mellea-api-xxxxx-xxxxx             1/1     Running   0          1m
# mellea-frontend-xxxxx-xxxxx        1/1     Running   0          1m
# redis-xxxxx-xxxxx                  1/1     Running   0          1m

# Check PVCs are bound
oc get pvc -n mellea-system

# Check routes are created
oc get routes -n mellea-system
```

### Step 5: Access the Application

Get the application URL:

```bash
# Get the frontend route URL
oc get route mellea-frontend -n mellea-system -o jsonpath='{.spec.host}'
```

The application will be available at `https://<route-hostname>/`.

## Configuration Options

### Custom Hostname

By default, OpenShift auto-generates hostnames. To use a custom domain:

```bash
# Patch both routes to use the same custom hostname
oc patch route mellea-frontend -n mellea-system \
  -p '{"spec":{"host":"mellea.your-domain.com"}}'
oc patch route mellea-api -n mellea-system \
  -p '{"spec":{"host":"mellea.your-domain.com"}}'
```

Ensure your DNS points to the OpenShift router's external IP.

### Custom StorageClass

The default PVCs use the cluster's default StorageClass. To specify a different one:

1. Edit `k8s/overlays/openshift/storage/persistent-volume-claims.yaml`
2. Add `storageClassName: your-storage-class` to each PVC spec

Or patch after deployment:

```bash
# Note: PVCs can only be patched before they're bound
# You may need to delete and recreate them
oc delete pvc -n mellea-system --all
# Edit the PVC manifests, then re-apply
oc apply -f k8s/overlays/openshift/storage/persistent-volume-claims.yaml
```

### Storage Size Adjustments

Default storage allocations:
- `mellea-assets-pvc`: 10Gi (program metadata)
- `mellea-workspaces-pvc`: 20Gi (workspace files)
- `mellea-artifacts-pvc`: 50Gi (build artifacts, logs)
- `mellea-redis-pvc`: 5Gi (Redis persistence)

To adjust, edit the PVC manifests before deployment or use `oc patch`:

```bash
oc patch pvc mellea-artifacts-pvc -n mellea-system \
  -p '{"spec":{"resources":{"requests":{"storage":"100Gi"}}}}'
```

### Image Registry

Images are pulled from `quay.io/psschwei/mellea-*` by default. To use a different registry:

1. Update image references in `k8s/base/backend/deployment.yaml` and `k8s/base/frontend/deployment.yaml`
2. Or create a kustomization overlay with image overrides:

```yaml
# In your custom overlay kustomization.yaml
images:
  - name: quay.io/psschwei/mellea-backend
    newName: your-registry.com/your-org/mellea-backend
    newTag: v1.0.0
  - name: quay.io/psschwei/mellea-frontend
    newName: your-registry.com/your-org/mellea-frontend
    newTag: v1.0.0
```

## Differences from KinD Deployment

| Aspect | KinD | OpenShift |
|--------|------|-----------|
| **Storage** | Local PersistentVolumes with manual paths | Dynamic provisioning via StorageClass |
| **Ingress** | Kubernetes Ingress with nginx | OpenShift Routes with HAProxy |
| **TLS** | Manual cert-manager setup | Automatic edge TLS termination |
| **Security** | Standard container security | Restricted SCC, arbitrary UID |
| **Init containers** | Uses root init container for permissions | Removed; uses fsGroup instead |
| **Images** | Loaded directly into cluster | Pulled from external registry |
| **Network** | NodePort fallback available | Routes only (ClusterIP services) |

### Key OpenShift Adaptations

1. **Security Context Constraints (SCC)**: OpenShift runs containers with arbitrary UIDs. The deployment patches:
   - Remove init containers that require root
   - Add `fsGroup: 0` to make volumes writable
   - Set `runAsNonRoot: true` with appropriate seccomp profiles

2. **Routes vs Ingress**: OpenShift Routes provide:
   - Automatic TLS with edge termination
   - Path-based routing (`/api` → backend, everything else → frontend)
   - Built-in HTTP/2 support

3. **Image Pull Secrets**: Unlike KinD where images are loaded directly, OpenShift pulls from a registry and needs authentication.

## Troubleshooting

### Pods Stuck in Pending

**Check PVC status:**
```bash
oc get pvc -n mellea-system
oc describe pvc mellea-assets-pvc -n mellea-system
```

Common causes:
- No default StorageClass configured
- Insufficient storage quota
- StorageClass doesn't support required access mode

**Fix:** Ensure a default StorageClass exists or specify one explicitly.

### ImagePullBackOff Errors

```bash
oc describe pod -n mellea-system -l app.kubernetes.io/name=mellea-api
```

Common causes:
- Missing or incorrect `registry-credentials` secret
- Wrong image name or tag
- Registry authentication issues

**Fix:** Verify the secret exists and has correct credentials:
```bash
oc get secret registry-credentials -n mellea-system -o yaml
# Test credentials manually:
podman login quay.io -u YOUR_USERNAME -p YOUR_PASSWORD
```

### Permission Denied Errors

If pods crash with permission errors on volume mounts:

```bash
oc logs -n mellea-system deployment/mellea-api
```

Common causes:
- Init container was not removed (SCC violation)
- fsGroup not set correctly

**Fix:** Ensure you're using the OpenShift overlay which includes the SCC-compatible patches:
```bash
oc apply -k k8s/overlays/openshift/
```

### Routes Not Working

```bash
oc get routes -n mellea-system
oc describe route mellea-frontend -n mellea-system
```

Common causes:
- Service selector doesn't match pods
- Route targeting wrong port
- TLS certificate issues

**Fix:** Verify services have endpoints:
```bash
oc get endpoints -n mellea-system
```

### API Requests Return 404

If the frontend loads but API calls fail:

1. Verify both routes share the same hostname
2. Check the API route has path `/api` configured
3. Verify the backend pod is healthy:

```bash
oc exec -n mellea-system deployment/mellea-api -- curl -s localhost:8000/health
```

## Updating the Deployment

To update to a new version:

```bash
# Pull latest manifests
git pull

# Re-apply (kustomize handles updates)
oc apply -k k8s/overlays/openshift/

# Or trigger a rollout with new images
oc set image deployment/mellea-api -n mellea-system \
  api=quay.io/psschwei/mellea-backend:v2.0.0
oc set image deployment/mellea-frontend -n mellea-system \
  frontend=quay.io/psschwei/mellea-frontend:v2.0.0
```

## Uninstalling

To remove all Mellea resources:

```bash
# Delete all resources created by the overlay
oc delete -k k8s/overlays/openshift/

# Or delete the entire namespace
oc delete namespace mellea-system
```

Note: Deleting PVCs will permanently delete stored data.
