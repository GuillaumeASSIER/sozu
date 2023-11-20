import sys

import anyio
import dagger


async def test():
    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:
        # get reference to the local project
        src = client.host().directory(".")

        # Cache volume
        rust_cache = client.cache_volume("rust")
        go_cache = client.cache_volume("go")
        #apt_cache = client.cache_volume("apt")

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
            .with_directory("/src", src, exclude=["ci.py", "test.toml"])
            .with_workdir("/src")
            # Cache
            .with_mounted_cache("~/.cargo/registry", rust_cache)
            .with_mounted_cache("~/.cargo/git", rust_cache)
            .with_mounted_cache("/target", rust_cache)
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
            .with_mounted_cache("~/.cargo/registry", rust_cache)
            .with_mounted_cache("~/.cargo/git", rust_cache)
            #.with_mounted_cache("/lagging_server/target", rust_cache)
            # Build
            .with_exec(["cargo", "build", "--release"])
        )

        container_bombardier = (
            client.container()
            .from_("golang:1.18.10-bullseye")
            # Cache
            .with_mounted_cache("/go/pkg/mod", go_cache)
            .with_mounted_cache("/root/.cache/go-build", go_cache)
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
            .from_("debian:12.2")
            # Cache
            #.with_mounted_cache("/var/lib/apt/lists/", apt_cache)
            # Retrieve executable
            .with_file("/bin/sozu", container_sozu.file("/src/target/release/sozu"))
            .with_exec(["apt", "update"])
            .with_exec(["apt", "install", "-y", "openssl"])
            .with_exec(["openssl", "genrsa", "-out", "lolcatho.st.key", "2048"])
            .with_exec(
                [
                    "openssl",
                    "req",
                    "-new",
                    "-x509",
                    "-key",
                    "lolcatho.st.key",
                    "-out",
                    "lolcatho.st.pem",
                    "-days" "365",
                    "-subj",
                    "CN=lolcatho.st",
                ]
            )
            .with_service_binding("lolcatho.st", service_receiver)
            .with_exec(["/bin/sozu", "-c", "ci/test.toml"])
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
        ).with_service_binding("sozu", service_sozu_RSA2048).with_exec(
            ["/bin/bombardier", "-c", "800", "-d", "60s", "https://sozu"]
        ).stdout())

    ##################
    # Run tests
    ##################

    print(test_run_https_800)

anyio.run(test)
