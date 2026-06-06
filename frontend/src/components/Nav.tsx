import { NavLink } from "react-router-dom";

/**
 * Top navigation bar. Uses react-router-dom NavLink so active items get
 * the `.active` class automatically.
 */
export default function Nav() {
  return (
    <nav className="nav">
      <NavLink to="/upload" className="nav-brand">
        finsight
      </NavLink>
      <ul className="nav-links">
        <li>
          <NavLink
            to="/upload"
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            Upload
          </NavLink>
        </li>
        <li>
          <NavLink
            to="/documents"
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            Documents
          </NavLink>
        </li>
        <li>
          <NavLink
            to="/companies"
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            Companies
          </NavLink>
        </li>
      </ul>
    </nav>
  );
}
