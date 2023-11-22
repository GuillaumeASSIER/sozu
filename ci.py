import sys
from datetime import datetime

import anyio
import dagger

SOZU_CONFIG = """


"""


async def test():
    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:

        ##################
        # Build containers
        ##################

        container_sozu = (
            client.container()
            .from_("fedora:39")
            # Install protbuf requirement
            .with_exec(["dnf","install","-y","rust","cargo","protobuf-compiler"])
            # Directory mapping
            .with_directory("/app", await client.host().directory(".", exclude=[".git","ci.py","**/ci"]))
            .with_workdir("/app")
            # Cache
            .with_mounted_cache("~/.cargo/registry", client.cache_volume("container_sozu_registry"))
            .with_mounted_cache("~/.cargo/git", client.cache_volume("container_sozu_git"))
            #.with_mounted_cache("/target", client.cache_volume("container_sozu_target"))
            # Build
            .with_exec(["cargo", "build", "--release"])
        )

        container_receiver = (
            client.container()
            .from_("fedora:39")
            .with_exec(["dnf", "install","-y","rust","cargo"])
            .with_directory("/app", client.git("https://github.com/Keksoj/lagging_server").branch("main").tree())
            # Cache
            .with_mounted_cache("~/.cargo/registry", client.cache_volume("container_receiver_registry"))
            .with_mounted_cache("~/.cargo/git", client.cache_volume("container_receiver_git"))
            .with_mounted_cache("/lagging_server/target", client.cache_volume("container_receiver_target"))
            # Build
            .with_workdir("/app")
            .with_exec(["cargo", "build", "--release"])
        )

        container_bombardier = (
            client.container()
            .from_("fedora:39")
            .with_exec(["dnf","install","-y","golang"])
            .with_env_variable("CGO_ENABLED", "0")
            .with_env_variable("GOPATH", "/go")
            .with_directory("/app", client.git("https://github.com/codesenberg/bombardier").branch("master").tree())
            # Cache
            .with_mounted_cache("$GOPATH/go/pkg/mod", client.cache_volume("container_receiver_mod"))
            .with_mounted_cache("~/.cache/go-build", client.cache_volume("container_receiver_go-build"))
            # Build
            .with_workdir("app")
            .with_exec(["go","build","-o","bombardier"])   
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
            .from_("fedora:39")
            # Retrieve executable
            .with_file(
                "/bin/lagging_server",
                container_receiver.file(
                    "/app/target/release/lagging_server"
                ),
            )
            .with_exec(["/bin/lagging_server", "--port", "4444"])
            .with_exposed_port(4444)
            .as_service()
        )

        service_sozu = (
            client.container()
            .from_("fedora:39")
            .with_exec(["dnf", "install", "-y", "openssl"])
            # Retrieve executable
            .with_file("/bin/sozu", container_sozu.file("/app/target/release/sozu"))
            # Mount CI
            .with_directory("/app", await client.host().directory(".", include=["ci/test.toml"]))
            .with_workdir("/app")
            .with_exec(["openssl", "req", "-newkey","rsa:2048","-nodes","-keyout","ci/sozu.io.key","-out","ci/sozu.io.csr","-subj","/CN=sozu.io"])
            .with_exec(["openssl", "x509", "-signkey","ci/sozu.io.key","-in","ci/sozu.io.csr","-req","-days","365","-out","ci/sozu.io.pem"])
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

        test_run_https_800 = await (
            client.container()
            .from_("fedora:39")
            .with_exec(["dnf","install","-y","openssl","curl"])
            # Retrieve executable
            .with_file("/bin/bombardier", container_bombardier.file("/app/bombardier"))
            .with_service_binding("sozu.io", service_sozu)
            .with_env_variable("CACHEBUSTER", str(datetime.now()))
            .with_exec(("curl","-vvv","-k","https://sozu.io:8443/api"))
            .with_exec(["/bin/bombardier", "-c", "800", "-d", "60s", "-k", "https://sozu.io:8443/api"])
            .stdout()
        )
        
    ##################
    # Run tests
    ##################

    print(test_run_https_800)

anyio.run(test)
