import sys
import json
import psi4
from pathlib import Path
from numpy import array as np_array
from argparse import ArgumentParser

def energy_calculator(xyz_file: Path,
                      method : str = 'scf',
                      basis_set : str = 'sto-3g') -> dict:
    """Calculate the energies of the XYZ files and write them to
    a JSON file."""

    psi4.set_output_file("energy_calculations.log", append=True)

    # with open(xyz_file, 'r') as f:
    #     mol = psi4.core.Molecule.from_file(f.read())
    # calc = psi4.geometry(mol.create_psi4_string_from_molecule())
    # calc_params = f"{method}/{basis_set}"
    # energy = psi4.energy(calc_params, molecule=calc)
    # grad = psi4.gradient(calc_params, molecule=calc)

    # return {"file": xyz_file,
    #         "energy": energy,
    #         "gradient": np_array(grad).tolist()}

    return {"file": str(xyz_file),
            "energy": 0.0,
            "gradient": [0.0, 0.0, 0.0]}

def main():
    parser = ArgumentParser(
                prog='Psi4 Simple Energy/Gradient Calculator',
                description=('Calculates the energy and gradient of a '
                             'molecule or a system of molecules using Psi4.'),
                epilog='Rony J. Letona 2026')

    parser.add_argument(
        '-x',
        '--xyz',
        type=Path,
        required=True,
        help='The file to read the coordinates from'
    )
    parser.add_argument(
        '-o',
        '--out',
        type=Path,
        required=True,
        help='The file where the data will be output'
    )
    parser.add_argument(
        '-m',
        '--method',
        type=str,
        default='scf',
        help=('The method to compute the energy and gradient. For more '
                'information visit https://psicode.org/psi4manual/1.9.x/'
                'methods.html or https://psicode.org/psi4manual/master/'
                'dft_byfunctional.html')
        )
    parser.add_argument(
        '-b',
        '--basisset',
        type=str,
        default='sto-3g',
        help=('The basis set for the calculation. For more information visit '
              'https://psicode.org/psi4manual/1.9.x/basissets_tables.html'
              '#apdx-basistables')
    )

    args = parser.parse_args()

    calculated = energy_calculator(xyz_file=args.xyz,
                                   method=args.method,
                                   basis_set=args.basisset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(calculated, indent=4))

    return 0

if __name__ == "__main__":
    sys.exit(main())