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

        # Containers
        container_sozu = (
                client.container()
                .from_("rust:1.70.0-bookworm")
                # Install protbuf requirement
                .with_exec(["apt-get", "update"])
                .with_exec(["apt-get", "install", "-y", "protobuf-compiler"])
                # Directory mapping
                .with_directory("/src", src, exclude=["ci.py", "test.toml"])
                .with_workdir("/src")
                # Build
                .with_exec(["cargo", "build", "--release"])
                # Cache
                .with_mounted_cache("~/.cargo/registry", rust_cache)
                .with_mounted_cache("~/.cargo/git", rust_cache)
                .with_mounted_cache("/target", rust_cache)
            )

        container_receiver = (
                client.container()
                .from_("rust:1.70.0-bookworm")
                .with_exec(["git", "clone", "https://github.com/Keksoj/lagging_server.git"])
                .with_workdir("/lagging_server")
                # Build
                .with_exec(["cargo", "build", "--release"])
                # Cache
                .with_mounted_cache("~/.cargo/registry", rust_cache)
                .with_mounted_cache("~/.cargo/git", rust_cache)
                .with_mounted_cache("/target", rust_cache)
            )
        
        container_bombardier = (
                client.container()
                .from_("golang:1.18.10-bullseye")
                # Build
                .with_env_variable("CGO_ENABLED", "0")
                .with_exec(["go", "install", "github.com/codesenberg/bombardier@latest"])
                # Cache
                .with_mounted_cache("~/go/pkg/mod", go_cache)
                .with_mounted_cache("~/.cache/go-build", go_cache)
            )
        
        service_receiver = {
                client.container()
                .from_("debian:bookworm")
                # Retrieve executable
                .with_file("/lagging_server/target/release/lagging_server", container_sozu.file("/bin/lagging_server"))
                .with_entrypoint(["/bin/lagging_server", "--port", "1054"])
                .with_exposed_port(1054)
                .as_service()
            }

        service_sozu = {
                client.container()
                .from_("debian:bookworm")
                # Directory mapping
                .with_directory("/src", src, exclude=["ci.py", "test.toml"])
                .with_workdir("/src")
                # Retrieve executable
                .with_file("/target/release/sozu", container_sozu.file("/bin/sozu"))
                .with_exec(["openssl", "genrsa", "-out", "lolcatho.st.key", "2048"])
                .with_exec(["openssl", "req", "-new", "-x509", "-key", "lolcatho.st.key", "-out", "lolcatho.st.pem", "-days" "365", "-subj", "CN=lolcatho.st"])
                .with_exec(["/bin/sozu", "-c", "test.toml"])
                .with_exposed_port(8443)
                .as_service()
            }

        async def container_executor(box):
            await box.sync()

        async with anyio.create_task_group() as tg:
            tg.start_soon(container_executor, container_sozu)
            tg.start_soon(container_executor, container_bombardier)
            tg.start_soon(container_executor, container_receiver)

        container_run_bombardier = (
                client.container()
                .from_("debian:bookworm")
                # Retrieve executable
                .with_file("~/go/bin/bombardier", container_bombardier.file("/bin/bombardier"))
                .with_service_binding("sozu", service_sozu)
                .with_exec(["/bin/bombardier -c 800 -d 60s https://sozu"])
                .stdout()
            )
        
anyio.run(test)
