import sys
import time
from datetime import datetime
from anyio import create_task_group

import anyio
import dagger

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
            .with_directory("/app", client.git("https://github.com/Sykursen/lagging_server").branch("main").tree())
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
        # Run
        ######################

        async def command_executor(command):
            await command

        service_receiver = (
            client.container()
            .from_("fedora:39")
            .with_exec(["dnf","install","-y","openssl","tmux"])
            # Mount CI
            .with_directory("/app", await client.host().directory(".", include=["ci/test.toml"]))
            .with_workdir("/app")
            .with_exec(["openssl", "req", "-newkey","rsa:2048","-nodes","-keyout","ci/sozu.io.key","-out","ci/sozu.io.csr","-subj","/CN=sozu.io"])
            .with_exec(["openssl", "x509", "-signkey","ci/sozu.io.key","-in","ci/sozu.io.csr","-req","-days","365","-out","ci/sozu.io.pem"])
            # Retrieve executables
            .with_file("/bin/lagging_server", container_receiver.file("/app/target/release/lagging_server"))
            .with_file("/bin/sozu", container_sozu.file("/app/target/release/sozu"))
            .with_file("/bin/bombardier", container_bombardier.file("/app/bombardier"))
            # .as_service()
            # .start()
        )

        async def lagging_server():
            return service_receiver.with_exec(["/bin/lagging_server","--port","4444"])
        
        async def sozu():
            return service_receiver.with_exec(["/bin/sozu","start","-c","ci/test.toml"])

        async def bombardier():
            time.sleep(3)
            # Bypass cache
            return (
                service_receiver.with_env_variable("CACHEBUSTER", str(datetime.now()))
                                .with_exec(("curl","-vvv","-k","https://sozu.io:8443/api"))
                                .with_exec(["/bin/bombardier","-c","800","-d","60s","-k","https://sozu.io:8443/api"])
            )

        async with create_task_group() as tg:
            tg.start_soon(command_executor, lagging_server())
            tg.start_soon(command_executor, sozu())
            tg.start_soon(command_executor, bombardier())
        
        #service_receiver.stop()

anyio.run(test)
