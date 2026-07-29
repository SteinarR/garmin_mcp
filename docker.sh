# UNUSED / STALE — does not reflect the real deployment.
# The `registry.ajlab.uk` registry below is incorrect: the server runs on
# fdlw.eu, not ajlab.uk. This script is not part of the actual build/deploy
# path. Safe to delete; kept here only until confirmed removable.

docker build --platform linux/amd64 -t sybadm/gramin-mcp:V1.0 -f Dockerfile .
docker tag sybadm/gramin-mcp:V1.0 registry.ajlab.uk/sybadm/gramin-mcp:V1.0
docker push  registry.ajlab.uk/sybadm/gramin-mcp:V1.0

