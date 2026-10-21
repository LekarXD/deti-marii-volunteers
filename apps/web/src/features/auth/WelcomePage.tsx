import {Link} from 'react-router-dom';
import welcomeArt from '../../assets/fund/welcome-art.webp';
import './auth.css';

export function WelcomePage() {
  return <section className="welcome-card" aria-labelledby="welcome-title"><div className="welcome-art"><img src={welcomeArt} alt=""/></div><div className="welcome-content"><h1 id="welcome-title">Добро пожаловать<br/>в «Дети Марии»</h1><p>Здесь мы знакомимся, учимся и готовимся к встречам с ребятами.</p><div className="welcome-actions"><Link className="btn btn-primary btn-lg" to="/login">Войти</Link><Link className="btn btn-secondary btn-lg" to="/register">Стать волонтёром</Link></div></div></section>;
}
