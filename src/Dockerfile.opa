# The policy engine with the platform's Rego baked in, run as a sidecar beside the
# gateway in Cloud Run. Policy changes ship as a new image through the same gate as
# everything else; nothing is mounted at runtime. Serves: BR-7, BR-8.
FROM openpolicyagent/opa:1.4.2
COPY provenance/gateway/policy /policy
ENTRYPOINT ["/opa"]
CMD ["run", "--server", "--addr", ":8181", "--log-level", "error", "/policy"]
