// SAMPLE DATA ONLY.
// Everything in this file is a hand-written, deterministic demonstration scenario ("orders-platform").
// It is NOT extracted from any repository: no scan, static analyzer or AI model produced it.
// The UI must always label anything derived from it as "sample".

export type LayerId = "frontend" | "api" | "service" | "repository" | "database" | "tests";

export interface LayerInfo {
  id: LayerId;
  label: string;
  short: string;
  color: string;
}

export const LAYERS: LayerInfo[] = [
  { id: "frontend", label: "Frontend (React / TypeScript)", short: "FRONTEND", color: "#38bdf8" },
  { id: "api", label: "API endpoints (FastAPI)", short: "API", color: "#a78bfa" },
  { id: "service", label: "Backend services", short: "SERVICE", color: "#34d399" },
  { id: "repository", label: "Repositories & models", short: "REPOSITORY", color: "#fbbf24" },
  { id: "database", label: "Database", short: "DATABASE", color: "#f472b6" },
  { id: "tests", label: "Automated tests", short: "TESTS", color: "#94a3b8" },
];

export const LAYER_BY_ID = Object.fromEntries(LAYERS.map((l) => [l.id, l])) as Record<LayerId, LayerInfo>;

export const SAMPLE_PROJECT = {
  name: "orders-platform",
  title: "orders-platform (sample)",
  description:
    "Illustrative e-commerce stack used to demonstrate cross-layer dependency graphs and change-impact analysis. Not a real repository.",
};

// ---------------------------------------------------------------------------------------------
// Sample source files (shown read-only in the Code tab of the sample workspace)
// ---------------------------------------------------------------------------------------------

export interface SampleFile {
  path: string;
  layer: LayerId;
  language: string;
  content: string;
}

export const SAMPLE_FILES: SampleFile[] = [
  {
    path: "frontend/src/types/order.ts",
    layer: "frontend",
    language: "typescript",
    content: `export interface Order {
  id: number;
  customer_id: number;
  total_cents: number;
  status: "pending" | "paid" | "shipped";
}
`,
  },
  {
    path: "frontend/src/components/OrderList.tsx",
    layer: "frontend",
    language: "typescript",
    content: `import { Order } from "../types/order";

interface Props {
  orders: Order[];
  customerId: number;
}

export function OrderList({ orders, customerId }: Props) {
  const mine = orders.filter((o) => o.customer_id === customerId);
  return (
    <ul>
      {mine.map((o) => (
        <li key={o.id}>
          Order #{o.id} (customer {o.customer_id}) - {o.status}
        </li>
      ))}
    </ul>
  );
}
`,
  },
  {
    path: "frontend/src/components/OrderDetails.tsx",
    layer: "frontend",
    language: "typescript",
    content: `import { Order } from "../types/order";

export function OrderDetails({ order }: { order: Order }) {
  return (
    <section>
      <h2>Order #{order.id}</h2>
      <a href={"/customers/" + order.customer_id}>View customer</a>
      <p>Status: {order.status}</p>
    </section>
  );
}
`,
  },
  {
    path: "frontend/src/components/CustomerCard.tsx",
    layer: "frontend",
    language: "typescript",
    content: `export function CustomerCard({ name, email }: { name: string; email: string }) {
  return (
    <article>
      <h3>{name}</h3>
      <p>{email}</p>
    </article>
  );
}
`,
  },
  {
    path: "backend/app/api/orders.py",
    layer: "api",
    language: "python",
    content: `from fastapi import APIRouter, Depends

from app.schemas.order import OrderOut
from app.services.order_service import OrderService, get_order_service

router = APIRouter()


@router.get("/api/orders", response_model=list[OrderOut])
async def list_orders(
    customer_id: int | None = None,
    service: OrderService = Depends(get_order_service),
):
    return await service.list_orders(customer_id)
`,
  },
  {
    path: "backend/app/api/customers.py",
    layer: "api",
    language: "python",
    content: `from fastapi import APIRouter, Depends

from app.services.customer_service import CustomerService, get_customer_service

router = APIRouter()


@router.get("/api/customers")
async def list_customers(service: CustomerService = Depends(get_customer_service)):
    return await service.list_customers()
`,
  },
  {
    path: "backend/app/schemas/order.py",
    layer: "api",
    language: "python",
    content: `from pydantic import BaseModel


class OrderOut(BaseModel):
    id: int
    customer_id: int
    total_cents: int
    status: str
`,
  },
  {
    path: "backend/app/services/order_service.py",
    layer: "service",
    language: "python",
    content: `from app.repositories.order_repository import OrderRepository


class OrderService:
    def __init__(self, repo: OrderRepository):
        self.repo = repo

    async def list_orders(self, owner: int | None):
        # Delegates by method name; never touches the column directly.
        return await self.repo.find_by_customer(owner)


def get_order_service() -> OrderService:
    ...  # dependency wiring omitted in this sample
`,
  },
  {
    path: "backend/app/services/customer_service.py",
    layer: "service",
    language: "python",
    content: `class CustomerService:
    def __init__(self, session):
        self.session = session

    async def list_customers(self):
        ...  # query on the customers table


def get_customer_service() -> CustomerService:
    ...  # dependency wiring omitted in this sample
`,
  },
  {
    path: "backend/app/repositories/order_repository.py",
    layer: "repository",
    language: "python",
    content: `from sqlalchemy import select

from app.models.order import Order


class OrderRepository:
    def __init__(self, session):
        self.session = session

    async def find_by_customer(self, customer_id: int | None):
        stmt = select(Order)
        if customer_id is not None:
            stmt = stmt.where(Order.customer_id == customer_id)
        return (await self.session.execute(stmt)).scalars().all()
`,
  },
  {
    path: "backend/app/models/order.py",
    layer: "repository",
    language: "python",
    content: `from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
`,
  },
  {
    path: "backend/app/models/customer.py",
    layer: "repository",
    language: "python",
    content: `from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
`,
  },
  {
    path: "database/schema.sql",
    layer: "database",
    language: "sql",
    content: `CREATE TABLE customers (
  id     INTEGER PRIMARY KEY,
  name   VARCHAR(120) NOT NULL,
  email  VARCHAR(255) NOT NULL
);

CREATE TABLE orders (
  id           INTEGER PRIMARY KEY,
  customer_id  INTEGER NOT NULL REFERENCES customers(id),
  total_cents  INTEGER NOT NULL,
  status       VARCHAR(16) NOT NULL
);

CREATE INDEX ix_orders_customer_id ON orders (customer_id);
`,
  },
  {
    path: "backend/tests/test_orders_api.py",
    layer: "tests",
    language: "python",
    content: `async def test_list_orders_filters_by_customer(client, seeded_orders):
    res = await client.get("/api/orders", params={"customer_id": 7})
    assert res.status_code == 200
    assert {o["customer_id"] for o in res.json()} == {7}
`,
  },
  {
    path: "backend/tests/test_order_repository.py",
    layer: "tests",
    language: "python",
    content: `from app.models.order import Order
from app.repositories.order_repository import OrderRepository


async def test_find_by_customer(session):
    session.add(Order(id=1, customer_id=7, total_cents=1200, status="paid"))
    await session.commit()
    rows = await OrderRepository(session).find_by_customer(7)
    assert [r.customer_id for r in rows] == [7]
`,
  },
  {
    path: "frontend/src/components/OrderList.test.tsx",
    layer: "tests",
    language: "typescript",
    content: `import { render, screen } from "@testing-library/react";
import { OrderList } from "./OrderList";

const orders = [
  { id: 1, customer_id: 7, total_cents: 1200, status: "paid" as const },
  { id: 2, customer_id: 9, total_cents: 800, status: "pending" as const },
];

test("shows only the customer's orders", () => {
  render(<OrderList orders={orders} customerId={7} />);
  expect(screen.getByText(/Order #1/)).toBeTruthy();
  expect(screen.queryByText(/Order #2/)).toBeNull();
});
`,
  },
  {
    path: "backend/tests/test_customers_api.py",
    layer: "tests",
    language: "python",
    content: `async def test_list_customers(client, seeded_customers):
    res = await client.get("/api/customers")
    assert res.status_code == 200
    assert len(res.json()) == 2
`,
  },
];

export const SAMPLE_FILE_BY_PATH = Object.fromEntries(SAMPLE_FILES.map((f) => [f.path, f])) as Record<string, SampleFile>;

// ---------------------------------------------------------------------------------------------
// Sample dependency graph
// Edge direction: "from depends on to" (arrow points at the thing being depended on).
// A "tested-by" edge points from a piece of code to the test that covers it.
// ---------------------------------------------------------------------------------------------

export interface GraphNodeData {
  id: string;
  label: string;
  layer: LayerId;
  kind: string;
  file: string;
  detail: string;
}

export interface GraphEdgeData {
  id: string;
  from: string;
  to: string;
  kind: "depends" | "tested-by";
  label: string;
}

export const GRAPH_NODES: GraphNodeData[] = [
  { id: "ui_list", label: "OrderList.tsx", layer: "frontend", kind: "React component", file: "frontend/src/components/OrderList.tsx", detail: "Renders the orders of one customer; filters on the order's customer id." },
  { id: "ui_details", label: "OrderDetails.tsx", layer: "frontend", kind: "React component", file: "frontend/src/components/OrderDetails.tsx", detail: "Order detail view; links to the customer using the order's customer id." },
  { id: "ui_type", label: "types/order.ts", layer: "frontend", kind: "TypeScript type", file: "frontend/src/types/order.ts", detail: "The Order interface; mirrors the API response shape." },
  { id: "ui_customer", label: "CustomerCard.tsx", layer: "frontend", kind: "React component", file: "frontend/src/components/CustomerCard.tsx", detail: "Shows one customer. Has no dependency on orders." },
  { id: "api_orders", label: "GET /api/orders", layer: "api", kind: "API endpoint", file: "backend/app/api/orders.py", detail: "Lists orders, optionally filtered by a customer_id query parameter." },
  { id: "api_schema", label: "OrderOut", layer: "api", kind: "Pydantic schema", file: "backend/app/schemas/order.py", detail: "Public response model for orders; its fields are the API contract." },
  { id: "api_customers", label: "GET /api/customers", layer: "api", kind: "API endpoint", file: "backend/app/api/customers.py", detail: "Lists customers." },
  { id: "svc_order", label: "OrderService", layer: "service", kind: "Service class", file: "backend/app/services/order_service.py", detail: "Business logic for orders; delegates queries to the repository." },
  { id: "svc_customer", label: "CustomerService", layer: "service", kind: "Service class", file: "backend/app/services/customer_service.py", detail: "Business logic for customers." },
  { id: "repo_order", label: "OrderRepository", layer: "repository", kind: "Repository", file: "backend/app/repositories/order_repository.py", detail: "Data access for orders (SQL filters on the customer column)." },
  { id: "model_order", label: "Order (model)", layer: "repository", kind: "SQLAlchemy model", file: "backend/app/models/order.py", detail: "ORM mapping of the orders table." },
  { id: "model_customer", label: "Customer (model)", layer: "repository", kind: "SQLAlchemy model", file: "backend/app/models/customer.py", detail: "ORM mapping of the customers table." },
  { id: "db_orders", label: "orders", layer: "database", kind: "Database table", file: "database/schema.sql", detail: "The orders table and its index on the customer column." },
  { id: "db_col", label: "orders.customer_id", layer: "database", kind: "Database column", file: "database/schema.sql", detail: "Foreign key from orders to customers." },
  { id: "db_customers", label: "customers", layer: "database", kind: "Database table", file: "database/schema.sql", detail: "The customers table." },
  { id: "t_ui", label: "OrderList.test.tsx", layer: "tests", kind: "Frontend test", file: "frontend/src/components/OrderList.test.tsx", detail: "Component test with order fixtures." },
  { id: "t_api", label: "test_orders_api.py", layer: "tests", kind: "Backend test", file: "backend/tests/test_orders_api.py", detail: "API test for the orders endpoint." },
  { id: "t_repo", label: "test_order_repository.py", layer: "tests", kind: "Backend test", file: "backend/tests/test_order_repository.py", detail: "Repository test against the orders table." },
  { id: "t_customers", label: "test_customers_api.py", layer: "tests", kind: "Backend test", file: "backend/tests/test_customers_api.py", detail: "API test for the customers endpoint." },
];

export const GRAPH_EDGES: GraphEdgeData[] = [
  { id: "e1", from: "ui_list", to: "ui_type", kind: "depends", label: "imports the Order type" },
  { id: "e2", from: "ui_details", to: "ui_type", kind: "depends", label: "imports the Order type" },
  { id: "e3", from: "ui_list", to: "api_orders", kind: "depends", label: "data comes from HTTP GET /api/orders" },
  { id: "e4", from: "ui_details", to: "api_orders", kind: "depends", label: "data comes from HTTP GET /api/orders" },
  { id: "e5", from: "ui_type", to: "api_schema", kind: "depends", label: "mirrors the API contract" },
  { id: "e6", from: "ui_customer", to: "api_customers", kind: "depends", label: "data comes from HTTP GET /api/customers" },
  { id: "e7", from: "api_orders", to: "api_schema", kind: "depends", label: "response_model" },
  { id: "e8", from: "api_orders", to: "svc_order", kind: "depends", label: "calls" },
  { id: "e9", from: "api_customers", to: "svc_customer", kind: "depends", label: "calls" },
  { id: "e10", from: "api_schema", to: "model_order", kind: "depends", label: "fields mirror the model" },
  { id: "e11", from: "svc_order", to: "repo_order", kind: "depends", label: "calls" },
  { id: "e12", from: "svc_customer", to: "model_customer", kind: "depends", label: "queries" },
  { id: "e13", from: "repo_order", to: "model_order", kind: "depends", label: "queries" },
  { id: "e14", from: "model_order", to: "db_orders", kind: "depends", label: "maps to table" },
  { id: "e15", from: "model_order", to: "db_col", kind: "depends", label: "maps column" },
  { id: "e16", from: "db_orders", to: "db_col", kind: "depends", label: "table contains column" },
  { id: "e17", from: "db_col", to: "db_customers", kind: "depends", label: "foreign key to customers.id" },
  { id: "e18", from: "model_customer", to: "db_customers", kind: "depends", label: "maps to table" },
  { id: "e19", from: "ui_list", to: "t_ui", kind: "tested-by", label: "covered by" },
  { id: "e20", from: "api_orders", to: "t_api", kind: "tested-by", label: "covered by" },
  { id: "e21", from: "repo_order", to: "t_repo", kind: "tested-by", label: "covered by" },
  { id: "e22", from: "api_customers", to: "t_customers", kind: "tested-by", label: "covered by" },
];

export const NODE_BY_ID = Object.fromEntries(GRAPH_NODES.map((n) => [n.id, n])) as Record<string, GraphNodeData>;

/** Direct dependencies of a node (what it needs). */
export function directDependencies(id: string): { node: GraphNodeData; label: string }[] {
  return GRAPH_EDGES.filter((e) => e.from === id && e.kind === "depends").map((e) => ({ node: NODE_BY_ID[e.to], label: e.label }));
}

/** Direct dependents of a node (what uses it), including tests that cover it. */
export function directDependents(id: string): { node: GraphNodeData; label: string }[] {
  return [
    ...GRAPH_EDGES.filter((e) => e.to === id && e.kind === "depends").map((e) => ({ node: NODE_BY_ID[e.from], label: e.label })),
    ...GRAPH_EDGES.filter((e) => e.from === id && e.kind === "tested-by").map((e) => ({ node: NODE_BY_ID[e.to], label: "tested by" })),
  ];
}

/** Everything that transitively depends on `id` (reverse reachability over "depends" edges). */
export function dependentsOf(id: string): string[] {
  const seen = new Set<string>();
  const queue = [id];
  while (queue.length) {
    const cur = queue.shift() as string;
    for (const e of GRAPH_EDGES) {
      if (e.kind === "depends" && e.to === cur && !seen.has(e.from)) {
        seen.add(e.from);
        queue.push(e.from);
      }
    }
  }
  return Array.from(seen);
}

/** Everything `id` transitively depends on. */
export function dependenciesOf(id: string): string[] {
  const seen = new Set<string>();
  const queue = [id];
  while (queue.length) {
    const cur = queue.shift() as string;
    for (const e of GRAPH_EDGES) {
      if (e.kind === "depends" && e.from === cur && !seen.has(e.to)) {
        seen.add(e.to);
        queue.push(e.to);
      }
    }
  }
  return Array.from(seen);
}

/** Downstream impact if `id` changes: its transitive dependents plus the tests covering any of them. */
export function impactOf(id: string): string[] {
  const code = new Set<string>([id].concat(dependentsOf(id)));
  const tests = GRAPH_EDGES.filter((e) => e.kind === "tested-by" && code.has(e.from)).map((e) => e.to);
  return Array.from(code).filter((c) => c !== id).concat(tests);
}

// ---------------------------------------------------------------------------------------------
// Sample change-impact scenario: rename a database column
// ---------------------------------------------------------------------------------------------

export type RiskLevel = "high" | "medium" | "low";

export interface ImpactItem {
  file: string;
  layer: LayerId;
  symbol: string;
  category: "direct" | "indirect";
  risk: RiskLevel;
  why: string;
  action: string;
}

export const SCENARIO = {
  id: "rename-customer-id",
  title: "Rename the column orders.customer_id to client_id",
  summary: "A database column rename that has to be followed through every layer that reads, exposes or tests it.",
  changedNodeId: "db_col",
  from: "customer_id",
  to: "client_id",
  overallRisk: "high" as RiskLevel,
  riskReasons: [
    "It is a schema migration on a table that is read by a live endpoint.",
    "The column name is part of the public API contract (query parameter and response field), so consumers outside this repository can break.",
    "The same identifier appears in 11 of 12 affected files, so a partial rename compiles in some layers and fails at runtime in others.",
  ],
  mitigations: [
    "Use an expand/contract migration: add client_id, backfill, switch reads, then drop customer_id.",
    "Keep customer_id as a deprecated API alias for one release.",
    "Run the three test files listed below before and after the change.",
  ],
  // Dependency path that explains why the frontend is affected by a database change
  path: ["orders.customer_id", "Order (model)", "OrderRepository", "OrderService", "GET /api/orders", "OrderOut", "types/order.ts", "OrderList.tsx", "OrderList.test.tsx"],
  newFile: "database/migrations/0002_rename_orders_customer_id.sql",
};

export const IMPACT_ITEMS: ImpactItem[] = [
  { file: "database/schema.sql", layer: "database", symbol: "orders.customer_id, ix_orders_customer_id", category: "direct", risk: "high", why: "The column and its index are defined here.", action: "Add a migration that renames the column and the index; update the schema file." },
  { file: "backend/app/models/order.py", layer: "repository", symbol: "Order.customer_id", category: "direct", risk: "high", why: "The ORM attribute maps the renamed column.", action: "Rename the attribute (or map it with name='client_id')." },
  { file: "backend/app/repositories/order_repository.py", layer: "repository", symbol: "OrderRepository.find_by_customer", category: "direct", risk: "high", why: "The SQL filter references Order.customer_id.", action: "Update the filter and the parameter name." },
  { file: "backend/app/schemas/order.py", layer: "api", symbol: "OrderOut.customer_id", category: "direct", risk: "high", why: "The response field is the public API contract.", action: "Rename the field and decide on a temporary alias for existing clients." },
  { file: "backend/app/api/orders.py", layer: "api", symbol: "list_orders(customer_id)", category: "direct", risk: "medium", why: "The query parameter is part of the public API.", action: "Rename the parameter; consider accepting the old name for one release." },
  { file: "backend/app/services/order_service.py", layer: "service", symbol: "OrderService.list_orders", category: "indirect", risk: "low", why: "Does not use the identifier; it calls find_by_customer, whose signature changes.", action: "No edit needed; review that the method naming still makes sense." },
  { file: "frontend/src/types/order.ts", layer: "frontend", symbol: "Order.customer_id", category: "direct", risk: "medium", why: "The TypeScript type mirrors the API response.", action: "Rename the field; the compiler will then flag every use." },
  { file: "frontend/src/components/OrderList.tsx", layer: "frontend", symbol: "o.customer_id", category: "direct", risk: "medium", why: "Filters orders on the field.", action: "Use the renamed field." },
  { file: "frontend/src/components/OrderDetails.tsx", layer: "frontend", symbol: "order.customer_id", category: "direct", risk: "medium", why: "Builds the customer link from the field.", action: "Use the renamed field." },
  { file: "backend/tests/test_orders_api.py", layer: "tests", symbol: "test_list_orders_filters_by_customer", category: "direct", risk: "low", why: "Sends the old query parameter and asserts on the old JSON key.", action: "Update the parameter and the assertion." },
  { file: "backend/tests/test_order_repository.py", layer: "tests", symbol: "test_find_by_customer", category: "direct", risk: "low", why: "Builds Order rows with the old attribute.", action: "Update the fixtures." },
  { file: "frontend/src/components/OrderList.test.tsx", layer: "tests", symbol: "orders fixture", category: "direct", risk: "low", why: "Fixtures use the old field name.", action: "Update the fixtures." },
];

// ---------------------------------------------------------------------------------------------
// Modification preview: deterministic before/after text and a small unified-diff builder
// ---------------------------------------------------------------------------------------------

export const MIGRATION_SQL = `-- Sample migration (preview only, not applied anywhere)
-- For large tables prefer expand/contract (add, backfill, switch, drop).
ALTER TABLE orders RENAME COLUMN customer_id TO client_id;
ALTER INDEX ix_orders_customer_id RENAME TO ix_orders_client_id;
`;

export interface FileChange {
  path: string;
  isNew: boolean;
  before: string;
  after: string;
  changedLines: number;
}

export function buildChanges(): FileChange[] {
  const changes: FileChange[] = IMPACT_ITEMS.map((item) => {
    const before = SAMPLE_FILE_BY_PATH[item.file].content;
    const after = before.split(SCENARIO.from).join(SCENARIO.to);
    const changedLines = before.split("\n").filter((line, i) => line !== after.split("\n")[i]).length;
    return { path: item.file, isNew: false, before, after, changedLines };
  });
  changes.push({ path: SCENARIO.newFile, isNew: true, before: "", after: MIGRATION_SQL, changedLines: MIGRATION_SQL.trimEnd().split("\n").length });
  return changes;
}

export type DiffLine = { t: "ctx" | "del" | "add"; text: string };
export interface Hunk {
  oldStart: number;
  newStart: number;
  oldCount: number;
  newCount: number;
  lines: DiffLine[];
}

const CONTEXT = 2;

/** Hunks for a change whose before/after have the same number of lines (a rename), or a brand-new file. */
export function buildHunks(change: FileChange): Hunk[] {
  if (change.isNew) {
    const lines = change.after.replace(/\n$/, "").split("\n");
    return [{ oldStart: 0, newStart: 1, oldCount: 0, newCount: lines.length, lines: lines.map((text) => ({ t: "add" as const, text })) }];
  }
  const a = change.before.replace(/\n$/, "").split("\n");
  const b = change.after.replace(/\n$/, "").split("\n");
  const changed: number[] = [];
  a.forEach((line, i) => {
    if (line !== b[i]) changed.push(i);
  });
  const hunks: Hunk[] = [];
  let i = 0;
  while (i < changed.length) {
    let start = Math.max(0, changed[i] - CONTEXT);
    let end = Math.min(a.length - 1, changed[i] + CONTEXT);
    let j = i + 1;
    while (j < changed.length && changed[j] - CONTEXT <= end + 1) {
      end = Math.min(a.length - 1, changed[j] + CONTEXT);
      j++;
    }
    const lines: DiffLine[] = [];
    let oldCount = 0;
    let newCount = 0;
    for (let k = start; k <= end; k++) {
      if (a[k] !== b[k]) {
        lines.push({ t: "del", text: a[k] }, { t: "add", text: b[k] });
        oldCount++;
        newCount++;
      } else {
        lines.push({ t: "ctx", text: a[k] });
        oldCount++;
        newCount++;
      }
    }
    hunks.push({ oldStart: start + 1, newStart: start + 1, oldCount, newCount, lines });
    i = j;
  }
  return hunks;
}

export function unifiedPatch(changes: FileChange[]): string {
  const out: string[] = [];
  for (const c of changes) {
    const hunks = buildHunks(c);
    if (!hunks.length) continue;
    out.push(`diff --git a/${c.path} b/${c.path}`);
    if (c.isNew) out.push("new file mode 100644");
    out.push(c.isNew ? "--- /dev/null" : `--- a/${c.path}`);
    out.push(`+++ b/${c.path}`);
    for (const h of hunks) {
      out.push(`@@ -${h.oldStart},${h.oldCount} +${h.newStart},${h.newCount} @@`);
      for (const l of h.lines) out.push((l.t === "del" ? "-" : l.t === "add" ? "+" : " ") + l.text);
    }
  }
  return out.join("\n") + "\n";
}
