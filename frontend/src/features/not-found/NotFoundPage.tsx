import { Link } from "react-router";

export default function NotFoundPage() {
  return (
    <section className="max-w-[720px] space-y-4">
      <h1>Page not found</h1>
      <p className="text-text-2">The page you requested does not exist.</p>
      <div>
        <Link to="/today" className="purvai-btn purvai-btn-primary">
          Back to Today
        </Link>
      </div>
    </section>
  );
}
