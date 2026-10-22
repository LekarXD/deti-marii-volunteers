import {Link} from 'react-router-dom';
import fundLogo from '../../assets/fund/marias-children-logo.svg';
import welcomeArt from '../../assets/fund/welcome-art.webp';
import {Card, Icon} from '../../ui';
import './auth.css';
import {PasswordLoginForm} from './LoginPage';

/** Entry for anonymous visitors: sign in right here, or start the volunteer application. */
export function WelcomePage() {
  return <div className="welcome"><Card className="welcome-login"><img className="welcome-logo" src={fundLogo} alt="Дети Марии" width="162" height="32"/><section className="welcome-login-body" aria-labelledby="welcome-title"><h1 id="welcome-title" className="h1">Вход в кабинет</h1><p className="auth-description">Для волонтёров и команды фонда</p><PasswordLoginForm/></section><p className="welcome-foot">Благотворительный фонд «Дети Марии» · <a href="https://mariaschildren.ru">mariaschildren.ru</a></p></Card><aside className="welcome-art" aria-labelledby="welcome-new-title"><img src={welcomeArt} alt=""/><div className="welcome-invite"><h2 id="welcome-new-title">Впервые у нас?</h2><p>Заполните анкету — координатор свяжется с вами и пригласит на собеседование.</p><Link className="btn btn-lg welcome-invite-action" to="/register">Стать волонтёром<Icon name="arrow-right"/></Link></div></aside></div>;
}
