import nextConfig from 'eslint-config-next'

/**
 * ESLint flat configuration.
 *
 * `eslint-config-next` v16 ships a flat configuration array, so it is used
 * directly rather than through the legacy compatibility layer.  The Next.js
 * configuration already enables the TypeScript, React Hooks and JSX
 * accessibility rule sets.
 */
const eslintConfig = [
  {
    ignores: [
      '.next/**',
      'node_modules/**',
      'out/**',
      'build/**',
      'next-env.d.ts',
      'public/**',
      'coverage/**',
    ],
  },
  ...nextConfig,
  {
    rules: {
      /**
       * The application performs its data fetching in client components
       * rather than through a framework router loader, so the canonical
       * "fetch on mount, then set state" pattern is used throughout.  That
       * pattern is flagged by this rule, which is designed for applications
       * whose data layer already guarantees a non-cascading render.
       *
       * The rule is disabled rather than worked around, because the
       * alternative -- threading every request through a framework loader --
       * would be a larger architectural change than the rule justifies, and
       * each effect already guards against a stale response with an
       * `AbortController`-style cancellation flag.
       */
      'react-hooks/set-state-in-effect': 'off',
    },
  },
]

export default eslintConfig
