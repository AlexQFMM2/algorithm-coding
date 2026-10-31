import * as esbuild from 'esbuild';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {readFile, writeFile, copyFile} from 'node:fs/promises';
const root = path.dirname(fileURLToPath(import.meta.url));
export const common = {
  bundle: true, platform: 'browser', format: 'esm', target: ['es2020'],
  loader: {'.js': 'jsx'},
  alias: {
    'core/tracers': path.join(root, 'upstream/tracers/index.js'),
    'core/renderers': path.join(root, 'upstream/renderers/index.js'),
    'core/layouts': path.join(root, 'upstream/layouts/index.js'),
    'components': path.join(root, 'src/components.jsx'),
    'common/util': path.join(root, 'src/util.js'),
  },
  define: {'process.env.NODE_ENV': '"production"'},
};
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await esbuild.build({...common, entryPoints: [path.join(root, 'src/index.jsx')],
    outfile: path.join(root, '../workbench/static/vendor/algorithm-visualizer/player.js'),
    minify: true, legalComments: 'linked'});
  const output = path.join(root, '../workbench/static/vendor/algorithm-visualizer');
  await copyFile(path.join(root, 'UPSTREAM.md'), path.join(output, 'README.md'));
  const licenses = ['upstream/LICENSE', 'node_modules/react/LICENSE', 'node_modules/react-dom/LICENSE', 'node_modules/sprintf-js/LICENSE'];
  await writeFile(path.join(output, 'LICENSES.txt'), (await Promise.all(licenses.map(async name => name + '\n\n' + await readFile(path.join(root, name), 'utf8')))).join('\n\n'));
}
