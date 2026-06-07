import {Config} from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setConcurrency(4);

// Serve the local `assets/` folder as the static/public directory so
// staticFile("screenshots/home.png") resolves to assets/screenshots/home.png.
Config.setPublicDir("assets");
