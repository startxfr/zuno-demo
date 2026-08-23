# ADR-0516: renders Mermaid source to SVG for mcp-gateway's generate_diagram
# handler. Alpine + the distro's own `chromium` package, not Puppeteer's
# bundled Chromium download (which ships glibc binaries that don't run on
# musl libc/Alpine) - the standard, documented workaround for Puppeteer on
# Alpine. PUPPETEER_SKIP_CHROMIUM_DOWNLOAD/PUPPETEER_EXECUTABLE_PATH below
# point puppeteer-core (a mermaid-cli dependency) at that system binary
# instead.
#
#   docker build -f components/diagram-render/Dockerfile -t zuno/diagram-render:dev components/diagram-render
#
# Defaults to the zuno-ai-build ImageStream mirror (ansible/roles/
# image_mirrors), not docker.io directly - same convention as every other
# Dockerfile in this repo (see components/agent-frontend/Dockerfile's own
# header comment). .github/workflows/build-publish.yml overrides this ARG
# to the real docker.io image for GitHub-hosted runners.
ARG BASE_IMAGE=image-registry.openshift-image-registry.svc:5000/zuno-ai-build/node:20-alpine
FROM ${BASE_IMAGE}

RUN apk add --no-cache \
    chromium \
    ca-certificates \
    ttf-freefont \
    font-noto-emoji

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser \
    NODE_ENV=production \
    # Restricted SCC runs this as a random non-root UID with no HOME -
    # same class of fix every Python Job in this repo already needs
    # (HOME=/tmp), Chromium/npm need their own writable HOME too.
    HOME=/tmp

WORKDIR /app
COPY package.json ./
# No package-lock.json committed (package.json's own ^-ranges are
# deliberately loose here - mermaid-cli/express patch releases are low-risk
# and this service has no reproducibility requirement stricter than "the
# latest compatible version renders correctly", unlike e.g.
# agent-frontend's `npm ci` which needs a committed lockfile for byte-
# identical UI builds).
RUN npm install --omit=dev
COPY server.js ./

# Restricted SCC: the container runs as an arbitrary non-root UID assigned
# by OpenShift, which must still be able to read/write everything under
# /app and /tmp (Chromium's own cache/profile dirs land there via HOME
# above) - group 0 + world-writable matches the standard OpenShift
# arbitrary-UID convention every other Dockerfile in this repo already
# follows for its own writable paths.
RUN chgrp -R 0 /app /tmp && chmod -R g=u /app /tmp

EXPOSE 8080
# Non-root placeholder UID, same convention as components/agent-frontend/
# Dockerfile's own USER 1001 - OpenShift's restricted-v2 SCC replaces this
# with a namespace-specific random UID at deploy time regardless (the
# group-0 chmod above is what actually makes that work, not this line).
USER 1001
CMD ["node", "server.js"]
