"""Keep automated tests isolated from personal real-provider configuration."""

import os


os.environ["RUNTIME_PROFILE"] = "test"
