import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://aiact.annotated.nl',
  output: 'static',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
});
