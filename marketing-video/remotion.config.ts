import {Config} from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setConcurrency(4);

// Serve the local `public/` folder as the static/public directory so
// staticFile("screenshots/home.png") resolves to public/screenshots/home.png.
Config.setPublicDir("public");
