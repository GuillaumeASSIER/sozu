import sys
import anyio
import dagger

async def test():
    config = dagger.Config(log_output=sys.stdout)

    src = client.host().directory(".")

    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:
        # get reference to the local project
        src = client.host().directory(".")

        python = (
            client.container().from_("cimg/rust:1.70")
            # Install protbuf requirement
            .with_exec(["apt-get", "update"])
            .with_exec(["apt-get", "install", "-y", "protobuf-compiler"])
            # mount cloned repository into image
            .with_directory("/", src)
            # set current working directory for next commands
            .with_workdir("/src")
            # Build sozu
            .with_exec(["cargo", "build", "--release"])
            # Run e2e tests
            .with_exec(["cargo", "test"])
        )

        build = {
            
        }

        # execute
        await python.sync()

    print("Tests succeeded!")

anyio.run(test)