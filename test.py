import sys
import anyio
import dagger

async def test():
    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:
        # get reference to the local project
        src = client.host().directory(".")

        python = (
            client.container().from_("rust:1.70.0-slim-bookworm")
            # Install protbuf requirement
            .with_exec(["sudo", "apt-get", "update"])
            .with_exec(["sudo", "apt-get", "install", "-y", "protobuf-compiler"])
            # mount cloned repository into image
            .with_directory("/", src)
            # set current working directory for next commands
            .with_workdir("/")
            # Build sozu
            .with_exec(["cargo", "build", "--release"])
            # Run e2e tests
            .with_exec(["cargo", "test"])
        )

        # execute
        await python.sync()

    print("Tests succeeded!")

anyio.run(test)