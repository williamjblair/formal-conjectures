# syntax=docker/dockerfile:1.7
FROM --platform=linux/amd64 ubuntu@sha256:019e8eb29a85e74d64925745884f2ec79aa27e3feab36353d24656f4d6b89467

ARG DEBIAN_FRONTEND=noninteractive
ARG UBUNTU_SNAPSHOT=20260810T000000Z
ARG UBUNTU_SNAPSHOT_URL=https://snapshot.ubuntu.com/ubuntu/${UBUNTU_SNAPSHOT}/

RUN rm -f /etc/apt/sources.list.d/ubuntu.sources \
    && printf '%s\n' \
      "deb [check-valid-until=no] ${UBUNTU_SNAPSHOT_URL} noble main universe" \
      "deb [check-valid-until=no] ${UBUNTU_SNAPSHOT_URL} noble-updates main universe" \
      > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false \
      -o Acquire::https::Verify-Peer=false update \
    && apt-get -o Acquire::https::Verify-Peer=false install -y \
      --no-install-recommends ca-certificates \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
      build-essential curl git jq libseccomp-dev pkg-config \
      python3 xz-utils zstd \
    && rm -rf /var/lib/apt/lists/*

ADD --checksum=sha256:708effb774be8237570d0add163225abbdfaf4fca28b2611df167beba4feef89 \
  https://go.dev/dl/go1.26.6.linux-amd64.tar.gz /tmp/go.tar.gz
ADD --checksum=sha256:056e2dc8564fc064a801e69f3eb18c044b9b546bc8b0e5a2c00247f8a1cb8ce6 \
  https://github.com/leanprover/lean4/releases/download/v4.27.0/lean-4.27.0-linux.tar.zst /tmp/lean.tar.zst

RUN mkdir -p /opt/go /opt/lean \
    && tar -xzf /tmp/go.tar.gz --strip-components=1 -C /opt/go \
    && tar --zstd -xf /tmp/lean.tar.zst --strip-components=1 -C /opt/lean \
    && rm /tmp/go.tar.gz /tmp/lean.tar.zst

ENV PATH="/opt/go/bin:/opt/lean/bin:${PATH}"

RUN git clone --filter=blob:none https://github.com/williamjblair/formal-conjectures.git /opt/formal-conjectures \
    && git -C /opt/formal-conjectures checkout 1f7b8ac102bbcac443288bc2f0620084db57422c \
    && test "$(git -C /opt/formal-conjectures rev-parse HEAD)" = 1f7b8ac102bbcac443288bc2f0620084db57422c \
    && git -C /opt/formal-conjectures fetch https://github.com/google-deepmind/formal-conjectures.git \
      2411d22e1bd550d050d0eac6c1fb379a76a3e7c5 \
    && git -C /opt/formal-conjectures update-ref refs/remotes/origin/main \
      2411d22e1bd550d050d0eac6c1fb379a76a3e7c5 \
    && git clone --filter=blob:none https://github.com/leanprover/comparator.git /opt/comparator \
    && git -C /opt/comparator checkout 71b52ec29e06d4b7d882726553b1ceb99a2499e0 \
    && test "$(git -C /opt/comparator rev-parse HEAD)" = 71b52ec29e06d4b7d882726553b1ceb99a2499e0 \
    && git clone --filter=blob:none https://github.com/Zouuup/landrun.git /opt/landrun \
    && git -C /opt/landrun checkout 5ed4a3db3a4ad930d577215c6b9abaa19df7f99f \
    && test "$(git -C /opt/landrun rev-parse HEAD)" = 5ed4a3db3a4ad930d577215c6b9abaa19df7f99f \
    && git clone --filter=blob:none https://github.com/leanprover/lean4export.git /opt/lean4export \
    && git -C /opt/lean4export checkout 590dec59d93ab6becdf16fdd8aee5abbb99cb856 \
    && test "$(git -C /opt/lean4export rev-parse HEAD)" = 590dec59d93ab6becdf16fdd8aee5abbb99cb856

ADD --checksum=sha256:792a4b5fab29e5855fbcb1115d54e28a054d8fcf7ee2bd5589834a73b387c052 \
  https://gist.githubusercontent.com/JohnEdwardJennings/e2c6ef0daab55857b7cc9d340de7af84/raw/8ff97800e38582c71246a238e7541a9d69488cbd/Erdos427.lean \
  /opt/inputs/Erdos427.lean

RUN cd /opt/landrun && go build -trimpath -o /usr/local/bin/landrun cmd/landrun/main.go \
    && cd /opt/lean4export && lake build lean4export \
    && cd /opt/comparator && lake build comparator

COPY scripts/comparator_outcome.py /opt/operator/comparator_outcome.py
COPY comparator/calibration/prepare_workspace.py /opt/operator/prepare_workspace.py
COPY comparator/calibration/container_execute.py /opt/operator/container_execute.py
COPY comparator/calibration/environment.lock.json /opt/operator/environment.lock.json
COPY comparator/calibration/erdos_427.toml /opt/operator/erdos_427.toml

RUN python3 /opt/operator/prepare_workspace.py

WORKDIR /opt/formal-conjectures/.comparator/erdos_427
ENTRYPOINT ["python3", "/opt/operator/container_execute.py"]
