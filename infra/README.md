# infra

Terraform for the platform, one module per plane, one root per environment, plus a
bootstrap root run once per project. The plain-language page is
`docs/10-foundation/11-cloud-substrate.md`; the pipeline that plans and applies this
tree is `docs/10-foundation/12-cicd-pipelines.md`.

```
bootstrap/          run once from an operator's machine: state bucket, keyless CI identity, deployers, registry
modules/
  delivery-plane/   what bootstrap creates
  data-plane/       lakehouse bucket, platform events topic
  context-plane/    gateway and evidence-server identities, the model-key secret
  agent-plane/      agent identities and what they may read
  assurance-plane/  event reader and its subscription
envs/
  dev/              the environment root CI plans on pull requests and applies on main
```

Project ids, bucket names, and anything else that names a real project live in
`*.tfvars` and `backend.hcl`, which git ignores; the `.example` twins show the shape.
