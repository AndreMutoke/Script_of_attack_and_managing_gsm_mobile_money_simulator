accounts = {
        "0990000001" : {
                "name" : "Agnes",
                "balance" : 1000
            },
        "0990000002" : {
                "name" :  "Andre",
                "balance" : 500
            }

        }
def show_balance(msisdn) :
    print(f"\nSolde actuel : {accounts[msisdn]['balance']} USD")

def transfer(sender, receiver, amount) :
    if sender not in accounts :
        print("Expéditeur inconnu")
        return
    if receiver not in accounts :
        print("Destinataire incounnu")
    if accounts[sender]["balance"] < amount :
        print("Solde insuffisant")
        return
    accounts[sender]["balance"] -= amount
    accounts[receiver]["balance"] += amount

    print("\n === Transfert réussi ===\n")
    print(f"{amount} USD envoyé De : {sender} vers {receiver}")

while True :
    print("\n === MOBILE MONEY ===\n")
    print("1. Consulter Solde")
    print("2. Envoyer Argent")
    print("3. Quitter")

    choice = input("Choix : ")

    if choice == "1" :
        msisdn = input("Numero : ")
        show_balance(msisdn)
    elif choice == "2" : 
        sender = input("Votre numero : ")
        receiver = input("Numero destinataire : ")
        amount = int( input("Montant : "))

        transfer(sender, receiver, amount)

    elif choice == "3" :
        break

    else :
        print("Choix invalide")
