# GKE Autopilot overlay for the homelab manifests in ../ -- the originals are
# untouched (the Jenkins/kind pipeline still uses them as-is). deploy-gcp.sh
# fills in the __PLACEHOLDERS__ below and writes kustomization.yaml (which is
# gitignored, since it contains your project ID and IP).
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

# ingress.yaml is deliberately NOT listed: it assumes ingress-nginx on kind.
# web-bff is exposed through a LoadBalancer Service instead (patched below).
resources:
  - ../namespace.yaml
  - ../postgres.yaml
  - ../cassandra.yaml
  - ../rabbitmq.yaml
  - ../prometheus.yaml
  - ../alertmanager.yaml
  - ../network-policies.yaml
  - ../user-service-deployment.yaml
  - ../user-service-service.yaml
  - ../social-graph-service-deployment.yaml
  - ../social-graph-service-service.yaml
  - ../post-service-deployment.yaml
  - ../post-service-service.yaml
  - ../engagement-service-deployment.yaml
  - ../engagement-service-service.yaml
  - ../story-service-deployment.yaml
  - ../story-service-service.yaml
  - ../messaging-service-deployment.yaml
  - ../messaging-service-service.yaml
  - ../feed-service-deployment.yaml
  - ../feed-service-service.yaml
  - ../notification-service-deployment.yaml
  - ../notification-service-service.yaml
  - ../media-service-deployment.yaml
  - ../media-service-service.yaml
  - ../gateway-deployment.yaml
  - ../gateway-service.yaml
  - ../web-bff-deployment.yaml
  - ../web-bff-service.yaml

images:
  - {name: localhost:5050/darviq-buzz-user-service, newName: __REGISTRY__/user-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-social-graph-service, newName: __REGISTRY__/social-graph-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-post-service, newName: __REGISTRY__/post-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-engagement-service, newName: __REGISTRY__/engagement-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-story-service, newName: __REGISTRY__/story-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-messaging-service, newName: __REGISTRY__/messaging-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-feed-service, newName: __REGISTRY__/feed-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-notification-service, newName: __REGISTRY__/notification-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-media-service, newName: __REGISTRY__/media-service, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-gateway, newName: __REGISTRY__/gateway, newTag: "__TAG__"}
  - {name: localhost:5050/darviq-buzz-web-bff, newName: __REGISTRY__/web-bff, newTag: "__TAG__"}

patches:
  # The committed buzz-secrets holds homelab-only plaintext credentials
  # ("buzz_password", a guessable JWT signing key). Never ship those to a
  # cluster with a public IP: drop it here, and deploy-gcp.sh creates the real
  # Secret from freshly generated random values instead.
  - patch: |-
      $patch: delete
      apiVersion: v1
      kind: Secret
      metadata:
        name: buzz-secrets
        namespace: darviq-buzz

  # web-bff is the only thing exposed to the internet, and only to the CIDR
  # the deployer supplied (there is no TLS here, so it must not be open to
  # the world: passwords and session cookies would cross the internet in
  # cleartext).
  - target: {kind: Service, name: web-bff}
    patch: |-
      - op: add
        path: /spec/type
        value: LoadBalancer
      - op: add
        path: /spec/loadBalancerSourceRanges
        value: ["__ALLOWED_CIDR__"]

  # The stock policy only admits the ingress-nginx namespace, which doesn't
  # exist here; a LoadBalancer's traffic would be dropped. The real gate is
  # loadBalancerSourceRanges above.
  - target: {kind: NetworkPolicy, name: web-bff-allow-ingress-controller}
    patch: |-
      - op: replace
        path: /spec/ingress/0/from
        value:
          - ipBlock: {cidr: 0.0.0.0/0}

  # NodePort -> ClusterIP: RabbitMQ management, Prometheus and Alertmanager
  # UIs are internal-only here (reach them with kubectl port-forward).
  - patch: |-
      apiVersion: v1
      kind: Service
      metadata: {name: rabbitmq, namespace: darviq-buzz}
      spec:
        type: ClusterIP
        ports:
          - {port: 15672, nodePort: null}
  - patch: |-
      apiVersion: v1
      kind: Service
      metadata: {name: prometheus, namespace: darviq-buzz}
      spec:
        type: ClusterIP
        ports:
          - {port: 9090, nodePort: null}
  - patch: |-
      apiVersion: v1
      kind: Service
      metadata: {name: alertmanager, namespace: darviq-buzz}
      spec:
        type: ClusterIP
        ports:
          - {port: 9093, nodePort: null}

  # Autopilot sets limits = requests, so the kind manifest's 4Gi *limit* would
  # become the request (and the bill) if left alone, while a 2Gi request
  # would cap it at 2Gi and OOM-kill it (the JVM needs heap + off-heap:
  # that's the exact failure seen on the homelab). 3Gi is the middle.
  - target: {kind: Deployment, name: cassandra}
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/resources
        value:
          requests: {cpu: "1", memory: 3Gi}
          limits: {cpu: "1", memory: 3Gi}

  # GCE persistent disks have a 10Gi minimum; ask for it explicitly rather
  # than relying on the provisioner rounding 1-2Gi requests up.
  - target: {kind: PersistentVolumeClaim, name: cassandra-data}
    patch: |-
      - {op: replace, path: /spec/resources/requests/storage, value: 10Gi}
  - target: {kind: PersistentVolumeClaim, name: postgres-data}
    patch: |-
      - {op: replace, path: /spec/resources/requests/storage, value: 10Gi}
  - target: {kind: PersistentVolumeClaim, name: media-uploads}
    patch: |-
      - {op: replace, path: /spec/resources/requests/storage, value: 10Gi}
