const https = require("https");

const packageName = process.argv[2];

if (!packageName) {
  process.stdout.write(JSON.stringify({ success: false, error: "No package name provided" }));
  process.exit(1);
}

const url = `https://registry.npmjs.org/${encodeURIComponent(packageName)}/latest`;

https
  .get(url, (res) => {
    let body = "";
    res.on("data", (chunk) => (body += chunk));
    res.on("end", () => {
      if (res.statusCode !== 200) {
        process.stdout.write(
          JSON.stringify({ success: false, error: `npm registry returned ${res.statusCode}` })
        );
        process.exit(1);
      }
      try {
        const pkg = JSON.parse(body);
        process.stdout.write(
          JSON.stringify({
            success: true,
            data: {
              name: pkg.name,
              version: pkg.version,
              description: pkg.description,
              license: pkg.license,
              homepage: pkg.homepage,
            },
          })
        );
      } catch {
        process.stdout.write(JSON.stringify({ success: false, error: "Failed to parse npm response" }));
        process.exit(1);
      }
    });
  })
  .on("error", (err) => {
    process.stdout.write(JSON.stringify({ success: false, error: err.message }));
    process.exit(1);
  });
