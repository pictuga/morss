<?php

define('FBAPPID', "<insert yours>");
define('FBSECRET', "<insert yours>");
define('FBAPPTOKEN', FBAPPID . '|' . FBSECRET);

if (isset($_GET['code']))
{
	# get real token from code
	$code = $_GET['code'];
	$eurl = sprintf("https://graph.facebook.com/oauth/access_token?client_id=%s&redirect_uri=%s&client_secret=%s&code=%s",
		FBAPPID, $_SERVER['SCRIPT_URI'], FBSECRET, $code);
	parse_str(file_get_contents($eurl), $values);
	$token = $values['access_token'];

	# get long-lived access token
	$eurl = sprintf("https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s",
		FBAPPID, FBSECRET, $token);
	parse_str(file_get_contents($eurl), $values);
	$ltoken = $values['access_token'];

	setcookie('token', $ltoken, 0, '/');

	# headers
	header('status: 303 See Other');
	header('location: http://' . $_SERVER['SERVER_NAME'] . '/');
}
