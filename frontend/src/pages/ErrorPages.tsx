import { Link } from "react-router";

import { BuiltBy } from "@/components/BuiltBy";

function ErrorShell({ code, title, message }: { code: string; title: string; message: string }) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-4 text-center">
      <p className="text-sm font-semibold text-brand-600">{code}</p>
      <h1 className="mt-2 text-2xl font-semibold text-slate-900">{title}</h1>
      <p className="mt-2 text-sm text-slate-500">{message}</p>
      <Link to="/" className="mt-6 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
        Go to my dashboard
      </Link>
      <BuiltBy className="mt-10" />
    </div>
  );
}

export const NotFoundPage = () => <ErrorShell code="404" title="Page not found" message="The page you're looking for doesn't exist." />;
export const ForbiddenPage = () => (
  <ErrorShell code="403" title="Access denied" message="Your role doesn't have access to this area." />
);
