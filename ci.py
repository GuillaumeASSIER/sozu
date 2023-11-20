import sys

import anyio
import dagger


async def test():
    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:
        # get reference to the local project
        src = client.host().directory(".")

        ##################
        # Build containers
        ##################

        container_sozu = (
            client.container()
            .from_("rust:1.70.0-bookworm")
            # Install protbuf requirement
            .with_exec(["apt", "update"])
            .with_exec(["apt", "install", "-y", "protobuf-compiler"])
            # Directory mapping
            .with_directory("/src", src)
            .with_workdir("/src")
            # Cache
            .with_mounted_cache("~/.cargo/registry", client.cache_volume("container_sozu_registry"))
            .with_mounted_cache("~/.cargo/git", client.cache_volume("container_sozu_git"))
            #.with_mounted_cache("/target", client.cache_volume("container_sozu_target"))
            # Build
            .with_exec(["cargo", "build", "--release"])
        )

        container_receiver = (
            client.container()
            .from_("rust:1.70.0-bookworm")
            .with_exec(
                ["git", "clone", "https://github.com/sykursen/lagging_server.git"]
            )
            .with_workdir("/lagging_server")
            # Cache
            .with_mounted_cache("~/.cargo/registry", client.cache_volume("container_receiver_registry"))
            .with_mounted_cache("~/.cargo/git", client.cache_volume("container_receiver_git"))
            #.with_mounted_cache("/lagging_server/target", client.cache_volume("container_receiver_target"))
            # Build
            .with_exec(["cargo", "build", "--release"])
        )

        container_bombardier = (
            client.container()
            .from_("golang:1.18.10-bullseye")
            # Cache
            .with_mounted_cache("/go/pkg/mod", client.cache_volume("container_receiver_mod"))
            .with_mounted_cache("/root/.cache/go-build", client.cache_volume("container_receiver_go-build"))
            # Build
            .with_env_variable("CGO_ENABLED", "0")
            .with_exec(["go", "install", "github.com/codesenberg/bombardier@latest"])   
        )

        async def container_executor(box):
            await box.sync()

        async with anyio.create_task_group() as tg:
            tg.start_soon(container_executor, container_sozu)
            tg.start_soon(container_executor, container_bombardier)
            tg.start_soon(container_executor, container_receiver)

        ######################
        # Services definitions
        ######################

        service_receiver = (
            client.container()
            .from_("debian:12.2")
            # Retrieve executable
            .with_file(
                "/bin/lagging_server",
                container_receiver.file(
                    "/lagging_server/target/release/lagging_server"
                ),
            )
            .with_exec(["/bin/lagging_server", "--port", "1054"])
            .with_exposed_port(1054)
            .as_service()
        )

        service_sozu_RSA2048 = (
            client.container()
            .from_("bitnami/debian-base-buildpack:bookworm-r0")
            # Cache
            #.with_mounted_cache("/var/lib/apt/lists/", apt_cache)
            # Retrieve executable
            .with_file("/bin/sozu", container_sozu.file("/src/target/release/sozu"))
            # Mount CI
            .with_directory("/src", src)
            .with_workdir("/src")
            .with_exec(["openssl", "genrsa", "-out", "ci/lolcatho.st.key", "2048"])
            .with_exec(
                [
                    "openssl",
                    "req",
                    "-new",
                    "-x509",
                    "-key",
                    "ci/lolcatho.st.key",
                    "-out",
                    "ci/lolcatho.st.pem",
                    "-days",
                     "365",
                    "-subj",
                    "/CN=lolcatho.st",
                ]
            )
            .with_service_binding("service_receiver", service_receiver)
            # Launch sozu
            .with_exec(["/bin/sozu", "start", "-c", "ci/test.toml"])
            .with_exposed_port(8080)
            .with_exposed_port(8443)
            .as_service()
        )

        ##################
        # Define tests
        ##################

        test_run_https_800 = await (client.container().from_("debian:12.2")
        # Retrieve executable
        .with_file(
            "/bin/bombardier", container_bombardier.file("/go/bin/bombardier")
        ).with_service_binding("lolcatho.st", service_sozu_RSA2048).with_exec(
            ["/bin/bombardier", "-c", "800", "-d", "60s", "https://lolcatho.st:8443"]
        ).stdout())

    ##################
    # Run tests
    ##################

    print(test_run_https_800)

anyio.run(test)
