import sys
import anyio
import dagger

async def test():
    config = dagger.Config(log_output=sys.stdout)

    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:
        # get reference to the local project
        src = client.host().directory(".")

        python = (
            # Image
            client.container().from_("rust:1.70.0-bookworm")

            # Install protbuf requirement
            .with_exec(["apt-get", "update"])
            .with_exec(["apt-get", "install", "-y", "protobuf-compiler"])

            # Install bombardier
            .with_exec(["apt-get", "install", "-y", "golang"])
            .with_exec(["go", "install", "github.com/codesenberg/bombardier@latest"])

            # mount cloned repository into image
            .with_directory("/src", src)
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